"""
module4/notifications.py
─────────────────────────
Alert notifications for CRITICAL and HIGH risk events.

Channels:
  - Slack webhook (SLACK_WEBHOOK_URL in .env)
  - SMTP email    (SMTP_* vars in .env) with PDF attachment

Both channels are optional — missing config is skipped gracefully.
Notifications are sent when a risk event is first detected at HIGH+ threshold.
"""

import logging
import os
import smtplib
import json
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from io import BytesIO
from typing import Optional

import requests
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors

load_dotenv()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  PDF Report Generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_risk_report_pdf(risk_events: list) -> bytes:
    """
    Generate a comprehensive PDF report with all risks and their alternatives.
    Returns PDF as bytes for email attachment.
    """
    from module1.db.session import get_session
    from module1.db.models import Supplier, Article, AlternateSupplier
    from module4.tools import get_alternates

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=12,
        fontName='Helvetica-Bold'
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#374151'),
        spaceAfter=8,
        spaceBefore=8,
        fontName='Helvetica-Bold'
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#4b5563'),
        spaceAfter=4
    )

    # Title
    story.append(Paragraph("Supply Chain Risk Report & Alternatives", title_style))
    story.append(Paragraph(f"Generated: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", normal_style))
    story.append(Spacer(1, 0.3*inch))

    # Summary
    critical_count = sum(1 for e in risk_events if e.severity_band == "CRITICAL")
    high_count = sum(1 for e in risk_events if e.severity_band == "HIGH")
    story.append(Paragraph(f"Summary: {critical_count} CRITICAL, {high_count} HIGH severity events", heading_style))
    story.append(Spacer(1, 0.2*inch))

    # Risk Events Table
    with get_session() as session:
        # Create header row with Paragraph objects for proper formatting
        header_style = ParagraphStyle(
            'TableHeader',
            parent=styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#ffffff'),
            alignment=1  # CENTER
        )
        
        cell_style = ParagraphStyle(
            'TableCell',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#374151'),
            alignment=0,  # LEFT
            wordWrap='CJK'  # Enable aggressive word wrapping
        )
        
        risk_data = [[
            Paragraph("Supplier", header_style),
            Paragraph("Score", header_style),
            Paragraph("Commodity", header_style),
            Paragraph("Severity", header_style),
            Paragraph("Event Type", header_style),
            Paragraph("Exposure", header_style),
        ]]
        
        for event in risk_events:
            supplier = session.query(Supplier).filter_by(id=event.supplier_id).first()
            supplier_name = supplier.name if supplier else "Unknown"
            
            risk_data.append([
                Paragraph(supplier_name, cell_style),
                Paragraph(f"{event.risk_score:.0f}", cell_style),
                Paragraph(event.commodity or "N/A", cell_style),
                Paragraph(event.severity_band or "N/A", cell_style),
                Paragraph((event.event_type or "N/A").replace("_", " ").title(), cell_style),
                Paragraph("Indirect" if event.is_indirect else "Direct", cell_style),
            ])

        # Risk table styling - better column widths with text wrapping and row height
        risk_table = Table(risk_data, colWidths=[1.8*inch, 0.5*inch, 1.5*inch, 0.8*inch, 1.3*inch, 0.7*inch])
        risk_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#374151')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#ffffff')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('ALIGN', (4, 0), (4, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('MINHEIGHT', (0, 1), (-1, -1), 0.8*inch),
        ]))
        
        story.append(risk_table)
        story.append(Spacer(1, 0.3*inch))

        # Alternatives Section
        story.append(Paragraph("Alternate Supplier Recommendations", heading_style))
        story.append(Spacer(1, 0.15*inch))

        for event in risk_events:
            supplier = session.query(Supplier).filter_by(id=event.supplier_id).first()
            supplier_name = supplier.name if supplier else "Unknown"
            
            story.append(Paragraph(f"<b>{supplier_name}</b> ({event.commodity or 'N/A'})", 
                                  ParagraphStyle('SubHeading', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold')))
            
            # Get alternatives
            alt_text = get_alternates(supplier_name=supplier_name)
            
            # Parse and display alternates
            alt_lines = alt_text.split('\n')
            for line in alt_lines[1:]:  # Skip header
                if line.strip() and line.startswith('#'):
                    # Parse alt line: "#1 Name (CODE) | Score: 78/100 | Capacity: high | Lead time: 3.0w"
                    story.append(Paragraph(f"  • {line.strip()}", normal_style))
            
            story.append(Spacer(1, 0.15*inch))

    # Build PDF
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes



# ─────────────────────────────────────────────────────────────────────────────
#  Slack
# ─────────────────────────────────────────────────────────────────────────────

def send_slack_alert(risk_event, supplier_name: str, article_headline: str = "") -> bool:
    """
    Send a Slack webhook notification for a HIGH/CRITICAL risk event.
    Returns True if sent successfully.
    """
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.debug("SLACK_WEBHOOK_URL not set — Slack notifications disabled")
        return False

    score = risk_event.risk_score
    band  = risk_event.severity_band or "UNKNOWN"

    # Slack colour: red for CRITICAL, orange for HIGH
    color = "#ef4444" if band == "CRITICAL" else "#f97316"

    # Band emoji
    emoji = "🚨" if band == "CRITICAL" else "⚠️"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji} Supply Chain {band} Alert"}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Supplier:*\n{supplier_name}"},
                {"type": "mrkdwn", "text": f"*Risk Score:*\n{score:.1f}/100"},
                {"type": "mrkdwn", "text": f"*Severity:*\n{band}"},
                {"type": "mrkdwn", "text": f"*Event Type:*\n{(risk_event.event_type or 'N/A').replace('_', ' ').title()}"},
                {"type": "mrkdwn", "text": f"*Commodity:*\n{risk_event.commodity or 'N/A'}"},
                {"type": "mrkdwn", "text": f"*Exposure:*\n{'Indirect (cascading)' if risk_event.is_indirect else 'Direct'}"},
            ]
        },
    ]

    if article_headline:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Trigger:* {article_headline[:200]}"}
        })

    if risk_event.impact_chain:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Propagation Pathway:*\n_{risk_event.impact_chain[:400]}_"}
        })

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"Supply Chain Risk Monitor · {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}]
    })

    payload = {
        "attachments": [{
            "color": color,
            "blocks": blocks,
        }]
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info(f"Slack alert sent for {supplier_name} [{band}]")
            return True
        else:
            logger.warning(f"Slack webhook returned {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")
        return False


def send_slack_briefing(briefing_text: str, title: str = "Weekly Risk Briefing") -> bool:
    """Send a text briefing to Slack."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return False

    payload = {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"📊 {title}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": briefing_text[:2900]}},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": f"Supply Chain Risk Monitor · {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}
            ]},
        ]
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"Slack briefing failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Email
# ─────────────────────────────────────────────────────────────────────────────

def _get_smtp_config() -> Optional[dict]:
    host = os.getenv("SMTP_HOST")
    if not host:
        return None
    return {
        "host":     host,
        "port":     int(os.getenv("SMTP_PORT", "587")),
        "user":     os.getenv("SMTP_USER", ""),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "from":     os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "")),
        "to":       os.getenv("ALERT_EMAIL_TO", ""),
        "use_tls":  os.getenv("SMTP_USE_TLS", "true").lower() == "true",
    }


def send_email_alerts_batch(risk_events: list) -> bool:
    """
    Send a single consolidated email with all HIGH/CRITICAL risk alerts.
    More efficient than sending individual emails for each alert.
    """
    cfg = _get_smtp_config()
    if not cfg or not cfg["to"]:
        logger.warning("Email config missing (SMTP_HOST or ALERT_EMAIL_TO)")
        return False
    
    if not risk_events:
        logger.debug("No risk events to email")
        return False

    from module1.db.session import get_session
    from module1.db.models import Supplier, Article

    # Build alert rows
    alert_rows = ""
    critical_count = 0
    high_count = 0

    with get_session() as session:
        for event in risk_events:
            supplier = session.query(Supplier).filter_by(id=event.supplier_id).first()
            article = session.query(Article).filter_by(id=event.article_id).first()
            
            supplier_name = supplier.name if supplier else "Unknown"
            band = event.severity_band or "UNKNOWN"
            
            if band == "CRITICAL":
                critical_count += 1
                color = "#ef4444"
            else:
                high_count += 1
                color = "#f97316"

            alert_rows += f"""
            <tr style="background: {'#fff5f5' if band == 'CRITICAL' else '#fff8f0'}; border-left: 4px solid {color};">
              <td style="padding: 12px; border-bottom: 1px solid #eee;">
                <div style="font-weight: bold; color: {color};">{"🚨" if band == "CRITICAL" else "⚠️"} {band}</div>
                <div style="font-size: 14px; margin-top: 4px;">{supplier_name}</div>
              </td>
              <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">{event.risk_score:.1f}</td>
              <td style="padding: 12px; border-bottom: 1px solid #eee;">{event.commodity or 'N/A'}</td>
              <td style="padding: 12px; border-bottom: 1px solid #eee; font-size: 12px; color: #666;">{(event.event_type or 'N/A').replace('_', ' ').title()}</td>
            </tr>
            """

    subject = f"[SC Risk] {critical_count + high_count} Alert(s) — {critical_count} CRITICAL, {high_count} HIGH"

    html = f"""
<html><body style="font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px;">
<div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; padding: 24px;">

  <h2 style="color: #1f2937; margin-top: 0; border-bottom: 3px solid #f97316; padding-bottom: 12px;">
    🚨 Risk Alert — {critical_count + high_count} Event(s)
  </h2>

  <div style="background: #fef2f2; border-left: 4px solid #ef4444; padding: 12px; margin: 16px 0; border-radius: 4px;">
    <strong style="color: #991b1b;">{critical_count} CRITICAL</strong> 
    <span style="color: #666;">, </span>
    <strong style="color: #b45309;">{high_count} HIGH</strong>
  </div>

  <p style="color: #4b5563; font-size: 14px; margin: 16px 0;">
    <strong>See the attached PDF report for:</strong>
  </p>
  <ul style="margin: 8px 0 0 0; padding-left: 20px; color: #4b5563; font-size: 14px;">
    <li>Complete risk details and analysis</li>
    <li>Recommended alternate suppliers with scores</li>
    <li>Supply chain recommendations</li>
  </ul>

  <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
  <p style="color: #999; font-size: 12px; margin: 0;">
    {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
  </p>
</div>
</body></html>
"""

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = cfg["from"]
        msg["To"] = cfg["to"]
        msg.attach(MIMEText(html, "html"))

        # Attach PDF report
        try:
            pdf_bytes = generate_risk_report_pdf(risk_events)
            pdf_attachment = MIMEBase('application', 'octet-stream')
            pdf_attachment.set_payload(pdf_bytes)
            encoders.encode_base64(pdf_attachment)
            pdf_attachment.add_header('Content-Disposition', 'attachment', filename='supply_chain_risk_report.pdf')
            msg.attach(pdf_attachment)
        except Exception as e:
            logger.warning(f"Could not attach PDF: {e}")

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            if cfg["use_tls"]:
                server.starttls()
            if cfg["user"] and cfg["password"]:
                server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from"], cfg["to"].split(","), msg.as_string())

        logger.info(f"Consolidated alert email sent ({len(risk_events)} events with PDF) to {cfg['to']}")
        return True
    except Exception as e:
        logger.error(f"Email alerts batch failed: {e}")
        return False


def send_email_briefing(briefing_text: str, title: str = "Supply Chain Analysis Report") -> bool:
    """Send the analysis briefing via email with PDF attachment."""
    from module1.db.session import get_session
    from module1.db.models import RiskEvent
    
    cfg = _get_smtp_config()
    if not cfg or not cfg["to"]:
        return False

    html = f"""
<html><body style="font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px;">
<div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; padding: 24px; border-top: 4px solid #f59e0b;">
  <h2 style="color: #1f2937; margin-top: 0;">
    📊 {title}
  </h2>
  
  <p style="color: #4b5563; font-size: 14px; margin: 16px 0;">
    See the attached PDF for:
  </p>
  <ul style="margin: 8px 0 0 0; padding-left: 20px; color: #4b5563; font-size: 14px;">
    <li>Complete risk analysis and statistics</li>
    <li>Recommended alternate suppliers</li>
    <li>Supply chain recommendations</li>
  </ul>
  
  <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
  <p style="color: #999; font-size: 12px; margin: 0;">
    {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
  </p>
</div>
</body></html>
"""

    try:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = f"[SC Risk] {title}"
        msg["From"]    = cfg["from"]
        msg["To"]      = cfg["to"]
        msg.attach(MIMEText(html, "html"))

        # Get all HIGH+ risk events for PDF
        with get_session() as session:
            threshold = float(os.getenv("ALERT_SCORE_THRESHOLD", "50"))
            risk_events = (
                session.query(RiskEvent)
                .filter(RiskEvent.risk_score >= threshold)
                .order_by(RiskEvent.risk_score.desc())
                .all()
            )
            
            # Attach PDF report
            if risk_events:
                try:
                    pdf_bytes = generate_risk_report_pdf(risk_events)
                    pdf_attachment = MIMEBase('application', 'octet-stream')
                    pdf_attachment.set_payload(pdf_bytes)
                    encoders.encode_base64(pdf_attachment)
                    pdf_attachment.add_header('Content-Disposition', 'attachment', filename='weekly_risk_report.pdf')
                    msg.attach(pdf_attachment)
                except Exception as e:
                    logger.warning(f"Could not attach PDF: {e}")

        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            if cfg["use_tls"]:
                server.starttls()
            if cfg["user"] and cfg["password"]:
                server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from"], cfg["to"].split(","), msg.as_string())

        logger.info(f"Email briefing with PDF sent to {cfg['to']}")
        return True
    except Exception as e:
        logger.error(f"Email briefing failed: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
#  Alert dispatcher — called after Module 2 scores a new HIGH+ event
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_risk_alert(risk_event, session) -> dict:
    """
    Send all configured notifications for a new HIGH+ risk event.
    Marks the event as alert_sent=True in the DB.

    Returns dict with channels that were successfully notified.
    """
    from module1.db.models import Supplier, Article

    supplier = session.query(Supplier).filter_by(id=risk_event.supplier_id).first()
    article  = session.query(Article).filter_by(id=risk_event.article_id).first()

    supplier_name = supplier.name if supplier else "Unknown Supplier"
    headline      = article.headline if article else ""

    results = {
        "slack": send_slack_alert(risk_event, supplier_name, headline),
        "email": send_email_alert(risk_event, supplier_name, headline),
    }

    # Mark as sent
    risk_event.alert_sent = True
    session.commit()

    notified = [k for k, v in results.items() if v]
    if notified:
        logger.info(f"Alerts dispatched via: {', '.join(notified)}")
    else:
        logger.debug("No notification channels configured (set SLACK_WEBHOOK_URL or SMTP_HOST)")

    return results


def check_and_dispatch_pending_alerts():
    """
    Find all HIGH+ risk events where alert_sent=False and dispatch notifications.
    Sends a single consolidated email with all pending alerts.
    Called after each Module 2 run.
    """
    try:
        from module1.db.session import get_session
        from module1.db.models import RiskEvent, Supplier, Article

        with get_session() as session:
            threshold = float(os.getenv("ALERT_SCORE_THRESHOLD", "50"))
            pending = (
                session.query(RiskEvent)
                .filter(
                    RiskEvent.risk_score >= threshold,
                    RiskEvent.alert_sent == False,
                )
                .order_by(RiskEvent.risk_score.desc())
                .all()
            )

            if not pending:
                logger.debug("No pending alerts to dispatch")
                return

            logger.info(f"Dispatching {len(pending)} risk events in consolidated email/Slack")
            
            # Send single consolidated email with all alerts
            email_sent = send_email_alerts_batch(pending)
            if email_sent:
                logger.info(f"Alert email sent to {os.getenv('ALERT_EMAIL_TO')}")
            
            # Send to Slack if configured (one Slack message per alert for visibility)
            slack_count = 0
            for event in pending:
                supplier = session.query(Supplier).filter_by(id=event.supplier_id).first()
                article = session.query(Article).filter_by(id=event.article_id).first()
                supplier_name = supplier.name if supplier else "Unknown"
                headline = article.headline if article else ""
                
                if send_slack_alert(event, supplier_name, headline):
                    slack_count += 1
            
            # Mark all as sent
            for event in pending:
                event.alert_sent = True
            session.commit()
            
            logger.info(f"Alerts dispatched: Email={'✓' if email_sent else '✗'}, Slack messages={slack_count}/{len(pending)}")

    except Exception as e:
        logger.error(f"Alert dispatch failed: {e}", exc_info=True)
