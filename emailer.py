"""
emailer.py — Sends the Markdown intelligence brief as a styled HTML email.

Reads configuration from environment variables:
  EMAIL_SMTP_HOST     SMTP server hostname  (default: smtp.gmail.com)
  EMAIL_SMTP_PORT     SMTP port             (default: 587, STARTTLS)
  EMAIL_FROM          Sender address        e.g. newsagent@yourco.com
  EMAIL_TO            Recipient(s)          comma-separated
  EMAIL_PASSWORD      SMTP password / app-password

For Gmail:
  • Enable 2-Step Verification on the Google account
  • Generate an App Password at myaccount.google.com/apppasswords
  • Use that 16-char password as EMAIL_PASSWORD
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger("news_agent.emailer")

# ── Brand colours (minimal, professional) ────────────────────────────────────
_PRIMARY   = "#1a1a2e"   # dark navy header
_ACCENT    = "#e94560"   # Blackstone-ish red accent
_BG        = "#f5f5f5"
_CARD_BG   = "#ffffff"
_TEXT      = "#333333"
_MUTED     = "#666666"
_BORDER    = "#e0e0e0"


class ReportEmailer:
    def __init__(self) -> None:
        self.smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("EMAIL_SMTP_PORT") or "587")
        self.from_addr = os.getenv("EMAIL_FROM", "")
        self.to_addrs  = [
            a.strip()
            for a in os.getenv("EMAIL_TO", "").split(",")
            if a.strip()
        ]
        self.password  = os.getenv("EMAIL_PASSWORD", "")
        self.enabled   = bool(self.from_addr and self.to_addrs and self.password)

        if not self.enabled:
            log.warning(
                "Email not configured — set EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD"
            )

    # ── public ──────────────────────────────────────────────────────────══[...]

    def send(self, report_md: str, run_date: str, qualifying_count: int) -> bool:
        if not self.enabled:
            return False

        subject = (
            f"AI × Real Estate Brief — {run_date} "
            f"({qualifying_count} top item{'s' if qualifying_count != 1 else ''})"
        )
        html_body  = self._build_html(report_md, run_date)
        plain_body = report_md

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = self.from_addr
        msg["To"]      = ", ".join(self.to_addrs)
        msg.attach(MIMEText(plain_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body,  "html",  "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as srv:
                srv.ehlo()
                srv.starttls()
                srv.ehlo()
                srv.login(self.from_addr, self.password)
                srv.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            log.info("Email sent → %s", ", ".join(self.to_addrs))
            return True
        except Exception as exc:
            log.error("Email send failed: %s", exc)
            return False

    # ── HTML builder ────────────────────────────────────────────────────────══[...]

    def _build_html(self, md: str, run_date: str) -> str:
        body_html = _md_to_html(md)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>AI × Real Estate Brief — {run_date}</title>
<style>
  body      {{ margin:0; padding:0; background:{_BG}; font-family: -apple-system,
              BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
              color:{_TEXT}; font-size:15px; line-height:1.6; }}
  .wrapper  {{ max-width:760px; margin:0 auto; background:{_CARD_BG}; }}
  .header   {{ background:{_PRIMARY}; color:#fff; padding:28px 36px 20px; }}
  .header h1{{ margin:0; font-size:22px; font-weight:700; letter-spacing:-0.3px; }}
  .header p {{ margin:6px 0 0; font-size:13px; color:#aab4c8; }}
  .content  {{ padding:28px 36px; }}
  h2        {{ color:{_PRIMARY}; font-size:17px; margin:28px 0 8px;
              border-bottom:2px solid {_ACCENT}; padding-bottom:4px; }}
  h3        {{ color:{_PRIMARY}; font-size:15px; margin:22px 0 6px; }}
  h4        {{ color:{_MUTED}; font-size:13px; margin:12px 0 4px;
              text-transform:uppercase; letter-spacing:0.5px; }}
  p         {{ margin:6px 0 12px; }}
  a         {{ color:{_ACCENT}; text-decoration:none; }}
  a:hover   {{ text-decoration:underline; }}
  ul        {{ padding-left:20px; margin:6px 0 12px; }}
  li        {{ margin:4px 0; }}
  hr        {{ border:none; border-top:1px solid {_BORDER}; margin:24px 0; }}
  .score-badge {{ display:inline-block; background:{_PRIMARY}; color:#fff;
                  font-size:12px; font-weight:600; padding:2px 8px;
                  border-radius:12px; margin-right:6px; }}
  .bx-badge    {{ display:inline-block; background:{_ACCENT}; color:#fff;
                  font-size:12px; font-weight:600; padding:2px 8px;
                  border-radius:12px; }}
  .label-simple   {{ font-weight:700; color:#2563eb; }}
  .label-technical{{ font-weight:700; color:#7c3aed; }}
  .footer   {{ background:#f0f0f0; padding:14px 36px; font-size:12px;
              color:{_MUTED}; border-top:1px solid {_BORDER}; }}
  table     {{ border-collapse:collapse; width:100%; margin:12px 0; }}
  th        {{ background:{_PRIMARY}; color:#fff; padding:7px 10px;
              font-size:13px; text-align:left; }}
  td        {{ padding:7px 10px; border-bottom:1px solid {_BORDER};
              font-size:13px; }}
  tr:nth-child(even) td {{ background:#f9f9f9; }}
  @media (max-width:600px) {{
    .content, .header, .footer {{ padding:18px 16px; }}
  }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>AI &times; Real Estate Intelligence Brief</h1>
    <p>Revantage &nbsp;|&nbsp; {run_date} &nbsp;|&nbsp; Powered by Claude AI</p>
  </div>
  <div class="content">
    {body_html}
  </div>
  <div class="footer">
    Generated by RevantageNewsAgent &nbsp;&bull;&nbsp; Scoring: max 120
    (R/25 &middot; U/25 &middot; A/25 &middot; Ap/25 &middot; BX/20)
    &nbsp;&bull;&nbsp; BX = Blackstone/Revantage Signal
  </div>
</div>
</body>
</html>"""


# ════════════════════════════════════════════════════════════════[...]
# Markdown → HTML converter (no external deps)
# ════════════════════════════════════════════════════════════════[...]

def _md_to_html(md: str) -> str:
    """
    Converts a subset of Markdown to HTML.
    Handles: h1–h4, bullet lists, horizontal rules, bold, italic, links,
    inline code, and paragraphs.
    """
    lines   = md.split("\n")
    out     = []
    in_ul   = False
    in_p    = False

    def close_ul():
        nonlocal in_ul
        if in_ul:
            out.append("</ul>")
            in_ul = False

    def close_p():
        nonlocal in_p
        if in_p:
            out.append("</p>")
            in_p = False

    for raw in lines:
        line = raw.rstrip()

        # Headings
        if line.startswith("#### "):
            close_ul(); close_p()
            out.append(f"<h4>{_inline(line[5:])}</h4>")
        elif line.startswith("### "):
            close_ul(); close_p()
            out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            close_ul(); close_p()
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            close_ul(); close_p()
            out.append(f"<h2>{_inline(line[2:])}</h2>")   # map h1→h2 inside email

        # Bullet list items
        elif re.match(r"^[-*]\s", line):
            close_p()
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_inline(line[2:])}</li>")

        # Numbered list
        elif re.match(r"^\d+\.\s", line):
            close_p()
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            content = re.sub(r"^\d+\.\s", "", line)
            out.append(f"<li>{_inline(content)}</li>")

        # Horizontal rule
        elif re.match(r"^-{3,}$", line.strip()) or re.match(r"^\*{3,}$", line.strip()):
            close_ul(); close_p()
            out.append("<hr/>")

        # Blank line
        elif line.strip() == "":
            close_ul(); close_p()

        # Table row (simple support)
        elif line.startswith("|"):
            close_ul(); close_p()
            cells = [c.strip() for c in line.strip("|").split("|")]
            if re.match(r"^[-: |]+$", line):          # separator row
                pass
            elif out and out[-1].startswith("<tr><th"):
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
            else:
                # first row → header
                if not any(t in out[-3:] for t in ["<table>", "<thead>"]):
                    out.append("<table>")
                out.append("<tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cells) + "</tr>")

        # Normal paragraph text
        else:
            close_ul()
            if not in_p:
                out.append("<p>")
                in_p = True
            else:
                out.append(" ")
            out.append(_inline(line))

    close_ul()
    close_p()

    # Close any open tables
    html = "\n".join(out)
    # Wrap table rows that aren't already in a table tag
    html = re.sub(r"(<table>(?:(?!</table>).)+)", r"\1</table>", html, flags=re.DOTALL)

    return html


def _inline(text: str) -> str:
    """Apply inline Markdown formatting: bold, italic, code, links."""
    # Inline code (do first to prevent inner processing)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold+italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    # Links [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^\)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    return text
