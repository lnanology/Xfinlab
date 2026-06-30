import os
import json
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# Colors
C_BG = HexColor('#080c14')
C_ACCENT = HexColor('#00d4ff')
C_GREEN = HexColor('#10b981')
C_RED = HexColor('#ef4444')
C_AMBER = HexColor('#f59e0b')
C_TEXT = HexColor('#e2e8f0')
C_MUTED = HexColor('#64748b')
C_SURFACE = HexColor('#0d1525')
C_PURPLE = HexColor('#7c3aed')


class ReportGenerator:
    """XFINLAB Report Generator - Creates professional PDF investment reports"""

    @staticmethod
    def generate(ticker: str, analysis: dict, research: dict, output_dir: str = "reports") -> str:
        """
        Generate a professional PDF investment report

        Args:
            ticker: Stock symbol
            analysis: Full analysis data from full_analysis endpoint
            research: AI research data from research endpoint
            output_dir: Directory to save PDF

        Returns:
            str: Path to generated PDF file
        """
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/{ticker}_report_{timestamp}.pdf"

        doc = SimpleDocTemplate(
            filename,
            pagesize=A4,
            rightMargin=20*mm,
            leftMargin=20*mm,
            topMargin=20*mm,
            bottomMargin=20*mm
        )

        styles = getSampleStyleSheet()
        story = []

        # Custom styles
        title_style = ParagraphStyle('Title', parent=styles['Normal'],
            fontSize=28, fontName='Helvetica-Bold',
            textColor=C_ACCENT, spaceAfter=4)

        subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'],
            fontSize=11, fontName='Helvetica',
            textColor=C_MUTED, spaceAfter=20)

        section_style = ParagraphStyle('Section', parent=styles['Normal'],
            fontSize=8, fontName='Helvetica-Bold',
            textColor=C_ACCENT, spaceBefore=16, spaceAfter=8,
            letterSpacing=1.5)

        body_style = ParagraphStyle('Body', parent=styles['Normal'],
            fontSize=9.5, fontName='Helvetica',
            textColor=C_TEXT, leading=16, spaceAfter=8)

        muted_style = ParagraphStyle('Muted', parent=styles['Normal'],
            fontSize=8, fontName='Helvetica',
            textColor=C_MUTED, spaceAfter=4)

        # ── Header ──────────────────────────────────────
        story.append(Paragraph("XFINLAB", title_style))
        story.append(Paragraph(f"Investment Research Report — {ticker}", subtitle_style))
        story.append(Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y %H:%M')}", muted_style))
        story.append(HRFlowable(width="100%", thickness=1, color=C_ACCENT, spaceAfter=20))

        # ── Score Summary Table ──────────────────────────
        story.append(Paragraph("INVESTMENT SCORES", section_style))

        final_score = analysis.get('final_score', 0)
        rating = analysis.get('rating', research.get('ai_recommendation', 'N/A'))

        def score_color(s):
            if s >= 70: return C_GREEN
            if s >= 45: return C_AMBER
            return C_RED

        score_data = [
            ['Metric', 'Score', 'Status'],
            ['Final Score', f"{final_score:.1f}", rating],
            ['Market Score', f"{analysis.get('market_score', 0):.1f}", ''],
            ['News Score', f"{analysis.get('news_score', 0):.1f}", ''],
            ['Strategy Score', f"{analysis.get('strategy_score', 0):.1f}", ''],
            ['Risk Score', f"{analysis.get('risk_score', 0):.1f}", analysis.get('risk', {}).get('risk_level', '')],
        ]

        score_table = Table(score_data, colWidths=[90*mm, 50*mm, 50*mm])
        score_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), C_SURFACE),
            ('TEXTCOLOR', (0,0), (-1,0), C_ACCENT),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,-1), HexColor('#0a1020')),
            ('TEXTCOLOR', (0,1), (-1,-1), C_TEXT),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,1), (-1,-1), 9),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [HexColor('#0a1020'), HexColor('#0d1525')]),
            ('GRID', (0,0), (-1,-1), 0.5, HexColor('#1e2d45')),
            ('PADDING', (0,0), (-1,-1), 8),
            ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 16))

        # ── Research Sections ────────────────────────────
        sections = [
            ('COMPANY OVERVIEW', 'company_overview'),
            ('FINANCIAL ANALYSIS', 'financial_analysis'),
            ('COMPETITIVE ADVANTAGE', 'competitive_advantage'),
            ('RISK FACTORS', 'risk_factors'),
            ('VALUATION', 'valuation'),
        ]

        for title, key in sections:
            val = research.get(key)
            if not val:
                continue
            story.append(Paragraph(title, section_style))
            if isinstance(val, dict):
                text = ' · '.join([f"{k}: {v}" for k, v in val.items()])
            else:
                text = str(val)
            story.append(Paragraph(text, body_style))

        # ── AI Verdict ───────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=1, color=C_SURFACE, spaceBefore=16, spaceAfter=16))
        story.append(Paragraph("AI VERDICT", section_style))

        confidence = research.get('confidence', 0)
        if confidence <= 1:
            confidence = int(confidence * 100)
        target = research.get('target_price', 'N/A')
        summary = research.get('summary', 'No summary available.')

        verdict_data = [
            ['Recommendation', 'Confidence', 'Target Price'],
            [str(research.get('ai_recommendation', 'HOLD')),
             f"{confidence}%",
             f"${target:.2f}" if isinstance(target, (int, float)) else str(target)],
        ]

        verdict_table = Table(verdict_data, colWidths=[63*mm, 63*mm, 64*mm])
        verdict_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), C_SURFACE),
            ('TEXTCOLOR', (0,0), (-1,0), C_ACCENT),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('BACKGROUND', (0,1), (-1,1), HexColor('#0a1020')),
            ('TEXTCOLOR', (0,1), (-1,1), C_GREEN),
            ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,1), (-1,1), 14),
            ('GRID', (0,0), (-1,-1), 0.5, HexColor('#1e2d45')),
            ('PADDING', (0,0), (-1,-1), 12),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ]))
        story.append(verdict_table)
        story.append(Spacer(1, 12))
        story.append(Paragraph(summary, body_style))

        # ── Disclaimer ───────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=1, color=C_SURFACE, spaceBefore=20, spaceAfter=12))
        story.append(Paragraph(
            "DISCLAIMER: This report is generated by XFINLAB AI and is for informational purposes only. "
            "It does not constitute financial advice. Always conduct your own research before making investment decisions.",
            muted_style))

        doc.build(story)
        return filename
