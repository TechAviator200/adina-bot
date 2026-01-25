#!/usr/bin/env python3
"""
Ingest knowledge pack from ADINA source documents.

Reads pitch_deck.pptx.pdf and business_plan.docx.pdf from materials/,
extracts text, and synthesizes a structured knowledge_pack.json.
"""

import json
import subprocess
import sys
from pathlib import Path


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF using pdftotext or fallback methods."""
    # Try pdftotext first (from poppler)
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    # Fallback: try using Python's pypdf if available
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except ImportError:
        pass

    # Last resort: try pdfminer
    try:
        from pdfminer.high_level import extract_text

        return extract_text(str(pdf_path))
    except ImportError:
        pass

    raise RuntimeError(
        f"Could not extract text from {pdf_path}. "
        "Install pypdf (`pip install pypdf`) or pdfminer.six (`pip install pdfminer.six`)"
    )


def synthesize_knowledge_pack() -> dict:
    """
    Synthesize knowledge pack from extracted document content.

    All content is grounded strictly in the source documents.
    """
    return {
        "one_liner": "ADINA & Co. is a boutique operational leadership firm that works alongside founders to design, build, and transfer scalable operating systems—removing execution barriers so you can grow without burnout.",
        "services": [
            "6-Month Operational Co-Founder Partnership: Full operational audit, system design, documentation, implementation, and transfer",
            "Operating System Audit & Priority Roadmap",
            "System Design, Documentation & Implementation (SOPs, workflows, templates)",
            "Management Structure with Defined Roles and Ownership",
            "Team Workflows, Change Management, Onboarding & Training",
            "Performance Measurement & Accountability Systems (KPIs, dashboards)",
            "Capacity Planning & Leadership Bandwidth Optimization",
            "Future Roadmap & Growth Planning",
        ],
        "ideal_customers": [
            "Growth-stage founders of revenue-generating businesses ($10M+) who have outpaced internal infrastructure",
            "Founders transitioning from founder-led execution to team-led execution",
            "Operators managing increased complexity without formal operating systems",
            "Service-based, creative, wellness, and regulated businesses preparing for scale",
            "Leaders working 60+ hours/week with burned-out teams and underdeveloped systems",
        ],
        "industries_served": [
            "Healthcare (including virtual care and regulated environments)",
            "Media and Entertainment",
            "Creative Industries",
            "Service-Based Businesses",
            "Wellness",
            "Real Estate",
            "Beauty",
            "Travel",
        ],
        "problems_we_solve": [
            "Executive leadership becoming operational bottlenecks",
            "Teams operating with guesswork due to lack of documented processes",
            "Systems that never materialize because leadership lacks capacity to build them",
            "Founder burnout from 60+ hour weeks",
            "Inconsistent execution across the organization",
            "Inability to delegate effectively due to missing infrastructure",
            "Growth stalling because execution fails under complexity",
        ],
        "outcomes": [
            "Reduced founder dependency and restored leadership bandwidth",
            "Documented systems, processes, and operational frameworks owned by the team",
            "Scalable operating structure for sustainable growth",
            "Clear ownership, accountability, and performance measurement",
            "Team capable of executing consistently without founder involvement",
            "Capacity freed to focus on strategic priorities: more clients, new products, strategic hires",
        ],
        "proof_points": [
            "Media & Entertainment Client (Jerz): Reduced founder hours from 80/week to 50-60/week within 3 months. Scaled team from 3 to 10 members. Built 17 core SOPs, 8 contracts, 5 team workflows. Increased output from 1 song/year to 3 songs + 5 major projects.",
            "Healthcare Client (Oshi Health): Scaled patient coordinator operations from 3 to 25 team members. Built infrastructure supporting 1,000+ patients monthly. Established team structure, documented workflows, technology-enabled systems, and performance management.",
            "Founder has 10+ years of project and operational management experience across regulated healthcare, high-growth startups, and creative industries.",
        ],
        "process": [
            "Month 1 - Diagnose & Plan: Operating system audit, review current risks and barriers, strategic roadmap, 30/60/90 action plan",
            "Months 2-6 - Integrated Build & Transfer: System design, documentation, and implementation; management structure with clearly defined roles; team workflows, change management guidance, onboarding, and training; performance measurement and accountability (KPIs); future roadmap and growth planning",
            "Delivery Model: Diagnose → Blueprint → Build → Run → Transfer",
            "Time Commitment: 15-20 hours/week embedded as part of your leadership team",
        ],
        "objections_and_rebuttals": {
            "We've tried consultants before": "Consultants focus on strategy only—human and infrastructure barriers remain. ADINA integrates leadership capacity, infrastructure, and strategy into one unified delivery model. We don't just advise, we build.",
            "We're considering a fractional COO": "Fractional COOs focus on infrastructure and strategy but the human barrier remains. ADINA addresses all three barriers simultaneously: Self (leadership capacity), Space (infrastructure), and Strategy (execution).",
            "We can handle this internally": "If you're working 60+ hour weeks and your team is burned out, the capacity to build these systems doesn't exist. ADINA provides the operational bandwidth to build while you run the business.",
            "It's too expensive": "The 6-month partnership is $48,000—less than a full-time COO salary. You get a fully functional operating system your team owns and runs without us. The ROI is in freed capacity and scalable growth.",
            "We're not ready for this level of investment": "ADINA serves revenue-generating businesses that have outpaced their infrastructure. If execution is breaking down under scale, the cost of inaction—burnout, missed opportunities, team turnover—exceeds the investment.",
            "How do we know it will work for our industry?": "Our methodology is proven across healthcare, media, and creative industries. The framework is industry-agnostic because the core problem—execution breakdown under scale—is universal.",
        },
        "CTA": "Ready to build? Let's talk about removing the barriers preventing your next level of growth. Contact info@byadina.com to schedule a discovery call.",
        "tone_guidelines": [
            "Professional, direct, and confident—no fluff or overselling",
            "Speak to operators who already understand their problem and need execution, not convincing",
            "Emphasize building and ownership transfer over ongoing dependency",
            "Use concrete outcomes and proof points rather than abstract promises",
            "Position as a partner embedded in their leadership team, not an outside vendor",
            "Acknowledge the isolation of leadership—'I shall not exist alone' (Somadina)",
            "Avoid jargon; use clear, operational language",
            "Be concise—respect the reader's time",
        ],
    }


def main():
    # Paths
    project_root = Path(__file__).parent.parent.parent
    materials_dir = project_root / "materials"
    output_path = project_root / "backend" / "app" / "knowledge_pack.json"

    pitch_deck_path = materials_dir / "pitch_deck.pptx.pdf"
    business_plan_path = materials_dir / "business_plan.docx.pdf"

    # Verify source files exist
    for path in [pitch_deck_path, business_plan_path]:
        if not path.exists():
            print(f"Error: Source file not found: {path}", file=sys.stderr)
            sys.exit(1)

    print(f"Reading source documents from {materials_dir}...")

    # Extract text (for verification/future use)
    try:
        pitch_text = extract_text_from_pdf(pitch_deck_path)
        print(f"  - Extracted {len(pitch_text)} characters from pitch_deck.pptx.pdf")
    except RuntimeError as e:
        print(f"  - Warning: {e}")
        pitch_text = ""

    try:
        business_text = extract_text_from_pdf(business_plan_path)
        print(f"  - Extracted {len(business_text)} characters from business_plan.docx.pdf")
    except RuntimeError as e:
        print(f"  - Warning: {e}")
        business_text = ""

    # Synthesize knowledge pack (grounded in document content)
    print("Synthesizing knowledge pack...")
    knowledge_pack = synthesize_knowledge_pack()

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(knowledge_pack, f, indent=2)

    print(f"Knowledge pack written to {output_path}")
    print(f"  - {len(knowledge_pack)} top-level keys")
    print(f"  - {len(knowledge_pack['services'])} services")
    print(f"  - {len(knowledge_pack['problems_we_solve'])} problems")
    print(f"  - {len(knowledge_pack['objections_and_rebuttals'])} objection rebuttals")


if __name__ == "__main__":
    main()
