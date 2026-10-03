"""Scores job-type classification against hand-labeled titles. Usage: python scripts/job_eval.py [rules|model]"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from healthsurface import classify  # noqa: E402

# title -> acceptable job types (first is preferred)
GOLD = {
    "Senior Battery Cell Engineer": ["Other"],
    "Technical Recruiting Lead": ["People and Recruiting"],
    "VP, Employer Sales - Pacific Northwest": ["Sales", "Executive and Admin"],
    "Revenue Accounting Manager": ["Finance and Accounting"],
    "Strategic Accounts Director, Large Group": ["Account Manager", "Sales"],
    "Telehealth Family Nurse Practitioner - Eating Disorders (New York-Remote)": ["Clinical Product Specialist"],
    "Software Engineer, Autonomous Revenue Operations (Brazil)": ["Software Engineer"],
    "Patient Success Manager": ["Customer Success Manager", "Customer Support"],
    "Caregiver Coach - Remote (EST)": ["Clinical Product Specialist", "Customer Support"],
    "Associate Clinical Oncology Specialist": ["Clinical Product Specialist", "Sales", "Medical Affairs and Science"],
    "Global Benefits Lead": ["People and Recruiting"],
    "Cloud Network Engineer": ["DevOps and Security"],
    "Senior Technical Recruiter": ["People and Recruiting"],
    "Account Executive - Central": ["Sales", "Account Manager"],
    "Director, Product Marketing": ["Product Marketing"],
    "Senior Product Designer": ["UX/UI Product Designer"],
    "Senior Analyst, SIU Investigator": ["Legal and Compliance"],
    "Strategic Account Executive Lodging": ["Sales", "Account Manager"],
    "Territory Manager (TX, Fort Bend)": ["Sales"],
    "Sr. Director of Machine Learning": ["AI Engineer"],
    "Senior Recruiter (Contract)": ["People and Recruiting"],
    "Lead Facilities Technician, Compounding": ["Operations and Strategy", "Other"],
    "Senior Automation Engineer": ["Software Engineer", "QA and Test", "Other"],
    "Manager, Growth": ["Growth and Lifecycle Marketing"],
    "Senior Manager, Talent Operations": ["People and Recruiting"],
    "VP of Engineering": ["Software Engineer", "Executive and Admin"],
    "Sales Development Representative (Utah)": ["Sales"],
    "Engineering Program Manager, New Product Development": ["Project or Program Manager"],
    "Menopause Provider (CNM/WHNP ) | MI License": ["Clinical Product Specialist"],
    "Senior/Staff Platform Engineer": ["DevOps and Security", "Software Engineer"],
    "Senior Manager, Revenue Cycle Management, Provider Operations": ["Operations and Strategy", "Finance and Accounting"],
    "Women's Mental Health Specialist (LCSW/LPC) | CO License": ["Clinical Product Specialist"],
    "Design Technologist": ["UX/UI Product Designer", "UI Engineer"],
    "Account Manager - Longevity": ["Account Manager"],
    "Account Sales Representative": ["Sales"],
    "Analytics Engineering Lead": ["Data and Analytics"],
    "Senior Manager, Venture Operations": ["Operations and Strategy"],
    "Associate Medical Director, Maternal and Pediatric Health": ["Clinical Product Specialist", "Medical Affairs and Science"],
    "Senior Director, Healthcare Product": ["Product Manager"],
    "External Data Specialist": ["Data and Analytics"],
    "Senior Scientist, Operations Investigation Team (OIT) #4936": ["Regulatory and Quality", "Medical Affairs and Science", "Other"],
    "Request for Proposal Manager (India)": ["Sales", "Partnerships and Business Development"],
    "Sr Manager, Global Regulatory Affairs (AI/ML)": ["Regulatory and Quality"],
    "Senior IT Engineer": ["DevOps and Security", "Software Engineer"],
    "Product Marketing Lead, Payor": ["Product Marketing"],
    "Senior Software Engineer": ["Software Engineer"],
    "Senior Strategic Accounts Manager (Mid-Market)": ["Account Manager"],
    "Senior Director, Member and Provider Services": ["Customer Support", "Operations and Strategy", "Executive and Admin"],
    "Fulfillment Pharmacist - Boynton Beach, FL": ["Clinical Product Specialist"],
    "Payroll & Equity Associate": ["Finance and Accounting", "People and Recruiting"],
    "Senior Health Economics and Outcomes Scientist": ["Medical Affairs and Science"],
    "Manager, Governance Risk & Compliance (GRC)": ["Legal and Compliance", "DevOps and Security"],
    "Growth/Digital Designer": ["Marketing Designer", "UX/UI Product Designer"],
}


def run(mode: str) -> None:
    invoke = None
    if mode == "model":
        from healthsurface.handlers import bedrock
        invoke = bedrock.invoke
    wrong = []
    for title, ok in GOLD.items():
        got = classify.classify_job({"title": title, "company": "a health company"}, invoke)[0]["job_type"]
        if got not in ok:
            wrong.append((title, got, ok[0]))
    print(f"{mode}: {len(GOLD) - len(wrong)}/{len(GOLD)} correct")
    for t, got, want in wrong:
        print(f"  {t[:60]:60} got {got!r:32} want {want!r}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "rules")
