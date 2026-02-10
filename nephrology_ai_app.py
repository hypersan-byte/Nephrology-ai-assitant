"""
AI-Powered Nephrology Clinical Assessment System
Processes dialysis data and generates comprehensive clinical reports
"""

import streamlit as st
import pandas as pd
import math
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# Page configuration
st.set_page_config(
    page_title="Nephrology AI Assistant",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better appearance
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stAlert {
        padding: 1rem;
        margin: 1rem 0;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    h1 {
        color: #1f4e78;
        border-bottom: 3px solid #4CAF50;
        padding-bottom: 0.5rem;
    }
    h2 {
        color: #2c5282;
        margin-top: 1.5rem;
    }
    .adequate {
        color: #2e7d32;
        font-weight: bold;
    }
    .marginal {
        color: #f57c00;
        font-weight: bold;
    }
    .inadequate {
        color: #c62828;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)


# ============= CALCULATION FUNCTIONS =============

class DialysisCalculations:
    """Core nephrology calculations"""
    
    @staticmethod
    def calculate_ktv(pre_urea, post_urea, hours, uf_volume, post_weight):
        """Calculate Kt/V using Daugirdas Second Generation Formula
        Works with urea in mmol/L (SI units)"""
        try:
            R = post_urea / pre_urea
            ln_component = -math.log(R - 0.008 * hours)
            uf_adjustment = (4 - 3.5 * R) * (uf_volume / post_weight)
            ktv = ln_component + uf_adjustment
            return round(ktv, 2)
        except (ZeroDivisionError, ValueError):
            return None
    
    @staticmethod
    def calculate_urr(pre_urea, post_urea):
        """Calculate Urea Reduction Ratio
        Works with urea in mmol/L (SI units)"""
        try:
            return round(((pre_urea - post_urea) / pre_urea) * 100, 1)
        except (ZeroDivisionError, ValueError):
            return None
    
    @staticmethod
    def calculate_ca_phos_product(calcium_mmol, phosphorus_mmol):
        """Calculate Calcium-Phosphorus Product in SI units
        Input: Ca in mmol/L, Phos in mmol/L
        Output: Product in (mmol/L)²
        Note: To convert to mg²/dL² multiply by 12.4"""
        return round(calcium_mmol * phosphorus_mmol, 2)
    
    @staticmethod
    def calculate_npcr(pre_urea, post_urea, hours, post_weight):
        """Calculate normalized Protein Catabolic Rate (simplified)
        Works with urea in mmol/L (SI units)"""
        try:
            # Simplified nPCR estimation
            urea_generation = (pre_urea - post_urea) * 0.58 * post_weight / hours
            npcr = (urea_generation * 0.33) / post_weight  # Adjusted for mmol/L
            return round(npcr, 2)
        except (ZeroDivisionError, ValueError):
            return None
    
    @staticmethod
    def interpret_ktv(ktv):
        """Interpret Kt/V adequacy"""
        if ktv is None:
            return "UNKNOWN", "gray", "Unable to calculate"
        if ktv >= 1.4:
            return "✓ ADEQUATE", "green", "No changes needed"
        elif ktv >= 1.2:
            return "⚠ MARGINAL", "orange", "Monitor closely"
        else:
            return "✗ INADEQUATE", "red", "Prescription change required"
    
    @staticmethod
    def assess_mineral_metabolism(ca_mmol, phos_mmol, pth_pmol):
        """Assess CKD-MBD status using SI units
        Ca: mmol/L (target 2.1-2.37)
        Phos: mmol/L (target 1.13-1.78)
        PTH: pmol/L (target 15.9-31.8)"""
        ca_phos = ca_mmol * phos_mmol
        issues = []
        
        if phos_mmol > 1.78:
            issues.append("Hyperphosphatemia")
        elif phos_mmol < 1.13:
            issues.append("Hypophosphatemia")
            
        if ca_mmol < 2.1:
            issues.append("Hypocalcemia")
        elif ca_mmol > 2.37:
            issues.append("Hypercalcemia")
            
        if pth_pmol > 31.8:
            issues.append("Elevated PTH (Secondary hyperparathyroidism)")
        elif pth_pmol < 15.9:
            issues.append("Low PTH (Adynamic bone disease risk)")
            
        # Ca×Phos product target < 4.4 (mmol/L)²
        if ca_phos > 4.4:
            issues.append("Elevated Ca×Phos product (Calcification risk)")
        
        status = "✓ ADEQUATE" if not issues else "⚠ ATTENTION NEEDED"
        color = "green" if not issues else "red"
        
        return {
            'status': status,
            'color': color,
            'issues': issues if issues else ['All parameters within target ranges'],
            'ca_phos': ca_phos
        }
    
    @staticmethod
    def assess_anemia(hgb_gl, ferritin_ugl, tsat):
        """Assess anemia management using SI units
        Hgb: g/L (target 100-115)
        Ferritin: µg/L (target ≥200)
        TSAT: % (target ≥20)"""
        issues = []
        
        if hgb_gl < 100:
            issues.append(f"Anemia (Hgb {hgb_gl} g/L, target 100-115)")
        elif hgb_gl > 115:
            issues.append(f"Hgb above target ({hgb_gl} g/L, target 100-115)")
            
        if ferritin_ugl < 200:
            issues.append(f"Low ferritin ({ferritin_ugl} µg/L, target ≥200)")
        elif ferritin_ugl > 500:
            issues.append(f"High ferritin ({ferritin_ugl} µg/L)")
            
        if tsat < 20:
            issues.append(f"Low TSAT ({tsat}%, target ≥20%)")
            
        # Determine iron deficiency type
        if ferritin_ugl < 200 and tsat < 20:
            iron_status = "Absolute iron deficiency"
        elif ferritin_ugl >= 200 and tsat < 20:
            iron_status = "Functional iron deficiency"
        else:
            iron_status = "Adequate iron stores"
        
        status = "✓ ADEQUATE" if not issues else "⚠ ATTENTION NEEDED"
        color = "green" if not issues else "orange"
        
        return {
            'status': status,
            'color': color,
            'issues': issues if issues else ['Anemia parameters within target'],
            'iron_status': iron_status
        }
    
    @staticmethod
    def assess_nutrition(albumin_gl, npcr):
        """Assess nutrition status using SI units
        Albumin: g/L (target ≥38)"""
        issues = []
        
        if albumin_gl < 38:
            if albumin_gl < 30:
                issues.append(f"Severe hypoalbuminemia ({albumin_gl} g/L)")
            else:
                issues.append(f"Low albumin ({albumin_gl} g/L, target ≥38)")
        
        if npcr and npcr < 1.0:
            issues.append(f"Low protein intake (nPCR {npcr} g/kg/day, target 1.0-1.2)")
        elif npcr and npcr > 1.2:
            issues.append(f"High protein intake (nPCR {npcr} g/kg/day)")
        
        status = "✓ ADEQUATE" if not issues else "⚠ ATTENTION NEEDED"
        color = "green" if not issues else "orange"
        
        return {
            'status': status,
            'color': color,
            'issues': issues if issues else ['Nutrition parameters adequate']
        }


# ============= AI REPORT GENERATION =============

def generate_ai_report(patient_data, calculations):
    """Generate comprehensive clinical report"""
    
    # Extract data
    labs = patient_data['labs']
    treatment = patient_data['treatment']
    calc = calculations
    
    # Generate report sections
    report = f"""
╔══════════════════════════════════════════════════════════╗
║     NEPHROLOGY CLINICAL ASSESSMENT REPORT               ║
╚══════════════════════════════════════════════════════════╝

Patient: {patient_data['patient_name']} (MRN: {patient_data['mrn']})
Date: {datetime.now().strftime('%B %d, %Y')}
Dialysis Unit: {patient_data['dialysis_unit']}
Reviewer: AI Clinical Assistant

───────────────────────────────────────────────────────────
1. DIALYSIS ADEQUACY ASSESSMENT
───────────────────────────────────────────────────────────

{calc['ktv_status']} - {calc['ktv_interpretation']}

Key Metrics:
• Kt/V: {calc['ktv']} (Target: ≥1.4)
• URR: {calc['urr']}% (Target: ≥65%)
• Treatment Time: {treatment['duration']} hours
• Blood Flow Rate: {treatment['blood_flow']} mL/min

Calculation Details:
• Pre-dialysis Urea: {labs['urea_pre']} mmol/L
• Post-dialysis Urea: {labs['urea_post']} mmol/L
• Ultrafiltration: {treatment['uf_volume']} L
• Post-dialysis weight: {treatment['post_weight']} kg

INTERPRETATION:
{_generate_adequacy_interpretation(calc['ktv'], calc['urr'])}

RECOMMENDATIONS:
{_generate_adequacy_recommendations(calc['ktv'], calc['urr'], treatment)}

───────────────────────────────────────────────────────────
2. MINERAL METABOLISM REPORT (CKD-MBD)
───────────────────────────────────────────────────────────

{calc['mineral']['status']}

Current Values:
• Calcium: {labs['calcium']} mmol/L (Target: 2.1-2.37)
• Phosphorus: {labs['phosphorus']} mmol/L (Target: 1.13-1.78)
• Ca×Phos Product: {calc['mineral']['ca_phos']} (mmol/L)² (Target: <4.4)
• Intact PTH: {labs['pth']} pmol/L (Target: 15.9-31.8)

Identified Issues:
{_format_issues(calc['mineral']['issues'])}

KDOQI/KDIGO Guideline Assessment:
{_generate_mineral_guidelines(labs['calcium'], labs['phosphorus'], labs['pth'])}

RECOMMENDATIONS:
{_generate_mineral_recommendations(calc['mineral']['issues'], labs)}

───────────────────────────────────────────────────────────
3. ANEMIA MANAGEMENT
───────────────────────────────────────────────────────────

{calc['anemia']['status']}

Current Values:
• Hemoglobin: {labs['hemoglobin']} g/L (Target: 100-115)
• Ferritin: {labs['ferritin']} µg/L (Target: ≥200)
• TSAT: {labs['tsat']}% (Target: ≥20%)

Iron Status: {calc['anemia']['iron_status']}

Identified Issues:
{_format_issues(calc['anemia']['issues'])}

RECOMMENDATIONS:
{_generate_anemia_recommendations(calc['anemia'], labs)}

───────────────────────────────────────────────────────────
4. NUTRITION ASSESSMENT
───────────────────────────────────────────────────────────

{calc['nutrition']['status']}

Current Values:
• Albumin: {labs['albumin']} g/L (Target: ≥38)
• nPCR: {calc['npcr']} g/kg/day (Target: 1.0-1.2)
• Post-dialysis weight: {treatment['post_weight']} kg

Identified Issues:
{_format_issues(calc['nutrition']['issues'])}

RECOMMENDATIONS:
{_generate_nutrition_recommendations(calc['nutrition'], labs)}

───────────────────────────────────────────────────────────
5. OVERALL SUMMARY & ACTION PLAN
───────────────────────────────────────────────────────────

PRIORITY LEVEL: {_determine_priority_level(calc)}

Key Clinical Issues:
{_summarize_key_issues(calc)}

IMMEDIATE ACTION ITEMS:
{_generate_action_items(calc, labs, treatment)}

FOLLOW-UP SCHEDULE:
• Labs in 4 weeks: CBC, BMP, Ca, Phos, PTH, Ferritin, TSAT
• Clinic visit: 4-6 weeks or sooner if issues arise
• Next monthly adequacy review: {_get_next_review_date()}

MEDICATION RECOMMENDATIONS:
{_generate_medication_recommendations(calc, labs)}

───────────────────────────────────────────────────────────
GUIDELINE REFERENCES
───────────────────────────────────────────────────────────
• KDOQI 2015 Hemodialysis Adequacy Guidelines
• KDIGO 2017 CKD-MBD Guidelines
• KDOQI 2020 Anemia Guidelines
• KDOQI/ASPEN 2020 Nutrition Guidelines

═══════════════════════════════════════════════════════════
Report generated by AI Clinical Assistant
Review Date: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}
═══════════════════════════════════════════════════════════
"""
    
    return report


# Helper functions for report generation

def _generate_adequacy_interpretation(ktv, urr):
    """Generate adequacy interpretation"""
    if ktv >= 1.4 and urr >= 65:
        return "Patient demonstrates adequate dialysis clearance. Current prescription is appropriate."
    elif ktv >= 1.2:
        return "Patient shows marginal dialysis adequacy. Close monitoring recommended. Consider prescription optimization."
    else:
        return "CRITICAL: Inadequate dialysis clearance. Immediate prescription adjustment required."

def _generate_adequacy_recommendations(ktv, urr, treatment):
    """Generate adequacy recommendations"""
    if ktv >= 1.4:
        return "• Continue current prescription\n• Monitor monthly adequacy"
    elif ktv >= 1.2:
        return f"• Consider increasing treatment time to {treatment['duration'] + 0.5} hours\n• Reassess Kt/V in 2-4 weeks\n• Ensure adequate blood flow and dialyzer function"
    else:
        return f"• URGENT: Increase treatment time to {treatment['duration'] + 1.0} hours\n• Consider increasing frequency to 4x/week\n• Verify vascular access function\n• Recheck Kt/V within 2 weeks"

def _generate_mineral_guidelines(ca_mmol, phos_mmol, pth_pmol):
    """Assess against guidelines using SI units"""
    assessment = []
    if 2.1 <= ca_mmol <= 2.37:
        assessment.append("✓ Calcium within KDIGO target range")
    else:
        assessment.append("✗ Calcium outside target range")
    
    if 1.13 <= phos_mmol <= 1.78:
        assessment.append("✓ Phosphorus within KDIGO target range")
    else:
        assessment.append("✗ Phosphorus requires intervention")
    
    if 15.9 <= pth_pmol <= 31.8:
        assessment.append("✓ PTH within target range")
    else:
        assessment.append("✗ PTH outside target range")
    
    return "\n".join(assessment)

def _generate_mineral_recommendations(issues, labs):
    """Generate CKD-MBD recommendations"""
    recs = []
    
    if "Hyperphosphatemia" in str(issues):
        recs.append("• Optimize phosphate binder regimen (consider dose increase)")
        recs.append("• Review binder adherence and timing with meals")
        recs.append("• Reinforce low-phosphorus diet counseling")
        recs.append("• Consider non-calcium binders if Ca×P elevated")
    
    if "Elevated PTH" in str(issues):
        recs.append("• Consider initiating/increasing vitamin D analog (calcitriol/paricalcitol)")
        recs.append("• If PTH >450 pg/mL, consider cinacalcet")
        recs.append("• Monitor calcium weekly after vitamin D adjustment")
    
    if "Low PTH" in str(issues):
        recs.append("• Hold vitamin D therapy")
        recs.append("• Assess for adynamic bone disease")
        recs.append("• Consider bone biopsy if persistent")
    
    if not recs:
        recs.append("• Continue current mineral management")
        recs.append("• Monitor labs monthly")
    
    recs.append("\n• Follow-up labs: Ca, Phos, PTH in 4 weeks")
    
    return "\n".join(recs)

def _generate_anemia_recommendations(anemia_data, labs):
    """Generate anemia management recommendations"""
    recs = []
    
    if "Absolute iron deficiency" in anemia_data['iron_status']:
        recs.append("• Initiate IV iron therapy:")
        recs.append("  - Iron sucrose 100 mg × 10 doses OR")
        recs.append("  - Ferric gluconate 125 mg × 8 doses")
        recs.append("• Target: Ferritin >200 µg/L, TSAT >25%")
    elif "Functional iron deficiency" in anemia_data['iron_status']:
        recs.append("• IV iron supplementation recommended despite adequate ferritin")
        recs.append("• Consider maintenance IV iron protocol")
    
    if labs['hemoglobin'] < 100:
        recs.append("• Hold ESA dose increase until after iron repletion")
        recs.append("• After iron: Consider ESA initiation/increase by 25%")
        recs.append("• Target Hgb 100-115 g/L (avoid >120 g/L)")
    
    recs.append("• Investigate potential bleeding sources")
    recs.append("• Follow-up labs: CBC, ferritin, TSAT in 4 weeks")
    
    return "\n".join(recs)

def _generate_nutrition_recommendations(nutrition_data, labs):
    """Generate nutrition recommendations"""
    recs = []
    
    if labs['albumin'] < 38:
        recs.append("• Dietitian referral for comprehensive nutrition assessment")
        recs.append("• Target protein intake: 1.2 g/kg/day")
        recs.append("• Check CRP to assess for inflammation vs malnutrition")
        
        if labs['albumin'] < 30:
            recs.append("• URGENT: Severe hypoalbuminemia - rule out protein losses")
            recs.append("• Consider intradialytic parenteral nutrition (IDPN)")
    
    recs.append("• Assess for barriers to adequate oral intake")
    recs.append("• Consider oral nutritional supplements")
    recs.append("• Monitor for protein-energy wasting signs")
    recs.append("• Follow-up: Albumin, nPCR in 4-6 weeks")
    
    return "\n".join(recs)

def _format_issues(issues):
    """Format issue list"""
    if not issues:
        return "• None identified"
    return "\n".join([f"• {issue}" for issue in issues])

def _determine_priority_level(calc):
    """Determine overall priority"""
    if calc['ktv'] and calc['ktv'] < 1.2:
        return "🔴 HIGH - Inadequate dialysis requires immediate attention"
    elif any("ATTENTION" in str(v.get('status', '')) for v in [calc['mineral'], calc['anemia'], calc['nutrition']]):
        return "🟡 MODERATE - Multiple parameters need optimization"
    else:
        return "🟢 LOW - Routine monitoring appropriate"

def _summarize_key_issues(calc):
    """Summarize all key issues"""
    issues = []
    
    if calc['ktv'] and calc['ktv'] < 1.4:
        issues.append(f"• Dialysis adequacy: Kt/V {calc['ktv']}")
    
    if calc['mineral']['issues'] and calc['mineral']['issues'][0] != 'All parameters within target ranges':
        issues.append(f"• Mineral metabolism: {', '.join(calc['mineral']['issues'][:2])}")
    
    if calc['anemia']['issues'] and calc['anemia']['issues'][0] != 'Anemia parameters within target':
        issues.append(f"• Anemia: {calc['anemia']['iron_status']}")
    
    if calc['nutrition']['issues'] and calc['nutrition']['issues'][0] != 'Nutrition parameters adequate':
        issues.append(f"• Nutrition: {calc['nutrition']['issues'][0]}")
    
    return "\n".join(issues) if issues else "• No critical issues identified"

def _generate_action_items(calc, labs, treatment):
    """Generate prioritized action items"""
    actions = []
    
    if calc['ktv'] and calc['ktv'] < 1.2:
        actions.append("☐ 1. URGENT: Adjust dialysis prescription (increase time/frequency)")
    
    if "Hyperphosphatemia" in str(calc['mineral']['issues']):
        actions.append("☐ 2. Optimize phosphate binder regimen")
    
    if labs['hemoglobin'] < 10.0:
        actions.append("☐ 3. Initiate IV iron supplementation")
    
    if labs['albumin'] < 3.5:
        actions.append("☐ 4. Urgent dietitian referral")
    
    if "Elevated PTH" in str(calc['mineral']['issues']):
        actions.append("☐ 5. Consider vitamin D therapy initiation/adjustment")
    
    if not actions:
        actions.append("☐ Continue current management")
        actions.append("☐ Schedule routine follow-up")
    
    return "\n".join(actions)

def _get_next_review_date():
    """Calculate next review date"""
    from datetime import timedelta
    next_date = datetime.now() + timedelta(days=30)
    return next_date.strftime('%B %d, %Y')

def _generate_medication_recommendations(calc, labs):
    """Generate specific medication recommendations"""
    meds = []
    
    if "Hyperphosphatemia" in str(calc['mineral']['issues']):
        meds.append("• Phosphate binder: [Specify agent and dose adjustment]")
    
    if "Elevated PTH" in str(calc['mineral']['issues']):
        meds.append("• Vitamin D: Consider calcitriol 0.25 mcg PO daily or paricalcitol")
    
    if labs['hemoglobin'] < 10.0:
        meds.append("• IV Iron: Iron sucrose 100 mg IV × 10 doses")
        meds.append("• ESA: Hold until after iron repletion, then reassess")
    
    if not meds:
        meds.append("• No medication changes recommended at this time")
    
    return "\n".join(meds)


# ============= PDF GENERATION =============

def generate_pdf_report(report_text, patient_name, mrn):
    """Generate professional PDF report"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    styles = getSampleStyleSheet()
    story = []
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1f4e78'),
        spaceAfter=12,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#2c5282'),
        spaceAfter=6,
        spaceBefore=12
    )
    
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=9,
        leading=12
    )
    
    # Title
    story.append(Paragraph("NEPHROLOGY CLINICAL ASSESSMENT REPORT", title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Patient info
    story.append(Paragraph(f"<b>Patient:</b> {patient_name} (MRN: {mrn})", normal_style))
    story.append(Paragraph(f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y')}", normal_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Parse and add report content
    for line in report_text.split('\n'):
        line = line.strip()
        
        if not line or line.startswith('═') or line.startswith('─') or line.startswith('╔'):
            continue
        
        # Section headers
        if line.endswith('ASSESSMENT') or line.endswith('REPORT') or line.endswith('MANAGEMENT') or line.endswith('SUMMARY & ACTION PLAN'):
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph(line, heading_style))
        else:
            # Regular content
            story.append(Paragraph(line.replace('•', '&bull;'), normal_style))
    
    # Build PDF
    doc.build(story)
    buffer.seek(0)
    return buffer


# ============= STREAMLIT UI =============

def main():
    """Main application"""
    
    st.title("🏥 AI-Powered Nephrology Clinical Assessment")
    st.markdown("### Automated Dialysis Adequacy & Clinical Review System")
    
    # Sidebar for patient info
    with st.sidebar:
        st.header("📋 Patient Information")
        
        patient_name = st.text_input("Patient Name", value="John Doe")
        mrn = st.text_input("MRN/ID", value="12345")
        dialysis_unit = st.text_input("Dialysis Unit", value="Downtown Dialysis Center")
        
        st.markdown("---")
        st.markdown("### 📊 Data Input Method")
        input_method = st.radio(
            "Choose input method:",
            ["Manual Entry", "CSV Upload (Coming Soon)"],
            help="Manual entry for quick testing, CSV for batch processing"
        )
        
        st.markdown("---")
        st.info("💡 **Tip:** Fill in all lab values and treatment data to generate a comprehensive report.")
    
    # Main content area with tabs
    tab1, tab2, tab3 = st.tabs(["📝 Data Entry", "📊 Report Preview", "ℹ️ About"])
    
    with tab1:
        st.header("Enter Patient Data")
        
        # Laboratory Values
        st.subheader("🔬 Laboratory Values")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("**Dialysis Labs**")
            urea_pre = st.number_input("Pre-dialysis Urea (mmol/L)", min_value=0.0, max_value=50.0, value=24.3, step=0.1, help="Normal: 2.5-7.5 mmol/L")
            urea_post = st.number_input("Post-dialysis Urea (mmol/L)", min_value=0.0, max_value=50.0, value=7.9, step=0.1, help="Target reduction: ≥65%")
            
        with col2:
            st.markdown("**Mineral Metabolism**")
            calcium = st.number_input("Calcium (mmol/L)", min_value=0.0, max_value=4.0, value=2.22, step=0.01, help="Target: 2.1-2.37 mmol/L")
            phosphorus = st.number_input("Phosphorus (mmol/L)", min_value=0.0, max_value=5.0, value=2.00, step=0.01, help="Target: 1.13-1.78 mmol/L")
            pth = st.number_input("Intact PTH (pmol/L)", min_value=0.0, max_value=200.0, value=51.3, step=0.1, help="Target: 15.9-31.8 pmol/L")
        
        with col3:
            st.markdown("**Anemia Parameters**")
            hemoglobin = st.number_input("Hemoglobin (g/L)", min_value=0.0, max_value=200.0, value=98.0, step=1.0, help="Target: 100-115 g/L")
            ferritin = st.number_input("Ferritin (µg/L)", min_value=0.0, max_value=2000.0, value=185.0, step=1.0, help="Target: ≥200 µg/L")
            tsat = st.number_input("TSAT (%)", min_value=0.0, max_value=100.0, value=22.0, step=1.0, help="Target: ≥20%")
        
        col4, col5 = st.columns(2)
        with col4:
            st.markdown("**Nutrition**")
            albumin = st.number_input("Albumin (g/L)", min_value=0.0, max_value=60.0, value=36.0, step=1.0, help="Target: ≥38 g/L")
        
        with col5:
            st.markdown("**Other Labs**")
            potassium = st.number_input("Potassium (mmol/L)", min_value=0.0, max_value=10.0, value=5.2, step=0.1, help="Normal: 3.5-5.0 mmol/L")
        
        st.markdown("---")
        
        # Treatment Data
        st.subheader("💉 Treatment Data")
        col6, col7, col8, col9 = st.columns(4)
        
        with col6:
            duration = st.number_input("Treatment Duration (hours)", min_value=0.0, max_value=8.0, value=4.0, step=0.5)
        with col7:
            uf_volume = st.number_input("Ultrafiltration (L)", min_value=0.0, max_value=10.0, value=2.5, step=0.1)
        with col8:
            post_weight = st.number_input("Post-dialysis Weight (kg)", min_value=0.0, max_value=200.0, value=75.5, step=0.1)
        with col9:
            blood_flow = st.number_input("Blood Flow (mL/min)", min_value=0, max_value=600, value=400, step=10)
        
        st.markdown("---")
        
        # Generate Report Button
        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
        with col_btn2:
            generate_button = st.button("🚀 Generate Clinical Report", type="primary", use_container_width=True)
        
        if generate_button:
            # Validate inputs
            if urea_pre <= 0 or urea_post <= 0 or post_weight <= 0 or duration <= 0:
                st.error("❌ Please ensure all required fields have valid values.")
                return
            
            with st.spinner("🔄 Analyzing patient data and generating report..."):
                # Calculate metrics
                calculator = DialysisCalculations()
                
                ktv = calculator.calculate_ktv(urea_pre, urea_post, duration, uf_volume, post_weight)
                urr = calculator.calculate_urr(urea_pre, urea_post)
                npcr = calculator.calculate_npcr(urea_pre, urea_post, duration, post_weight)
                
                ktv_status, ktv_color, ktv_interpretation = calculator.interpret_ktv(ktv)
                mineral_assessment = calculator.assess_mineral_metabolism(calcium, phosphorus, pth)
                anemia_assessment = calculator.assess_anemia(hemoglobin, ferritin, tsat)
                nutrition_assessment = calculator.assess_nutrition(albumin, npcr)
                
                # Store in session state
                st.session_state['patient_data'] = {
                    'patient_name': patient_name,
                    'mrn': mrn,
                    'dialysis_unit': dialysis_unit,
                    'labs': {
                        'urea_pre': urea_pre,
                        'urea_post': urea_post,
                        'calcium': calcium,
                        'phosphorus': phosphorus,
                        'pth': pth,
                        'hemoglobin': hemoglobin,
                        'ferritin': ferritin,
                        'tsat': tsat,
                        'albumin': albumin,
                        'potassium': potassium
                    },
                    'treatment': {
                        'duration': duration,
                        'uf_volume': uf_volume,
                        'post_weight': post_weight,
                        'blood_flow': blood_flow
                    }
                }
                
                st.session_state['calculations'] = {
                    'ktv': ktv,
                    'urr': urr,
                    'npcr': npcr,
                    'ktv_status': ktv_status,
                    'ktv_color': ktv_color,
                    'ktv_interpretation': ktv_interpretation,
                    'mineral': mineral_assessment,
                    'anemia': anemia_assessment,
                    'nutrition': nutrition_assessment
                }
                
                # Generate AI report
                report_text = generate_ai_report(st.session_state['patient_data'], st.session_state['calculations'])
                st.session_state['report_text'] = report_text
                
            st.success("✅ Report generated successfully! Switch to the 'Report Preview' tab to view.")
    
    with tab2:
        st.header("Clinical Assessment Report")
        
        if 'report_text' in st.session_state:
            # Display quick metrics at top
            st.subheader("📊 Quick Metrics Dashboard")
            
            calc = st.session_state['calculations']
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                ktv_val = calc['ktv'] if calc['ktv'] else "N/A"
                delta_color = "normal" if calc['ktv'] and calc['ktv'] >= 1.4 else "inverse"
                st.metric("Kt/V", ktv_val, calc['ktv_status'], delta_color=delta_color)
            
            with col2:
                urr_val = calc['urr'] if calc['urr'] else "N/A"
                delta_color = "normal" if calc['urr'] and calc['urr'] >= 65 else "inverse"
                st.metric("URR", f"{urr_val}%", calc['ktv_status'], delta_color=delta_color)
            
            with col3:
                ca_phos = calc['mineral']['ca_phos']
                delta_color = "normal" if ca_phos < 55 else "inverse"
                st.metric("Ca×Phos", ca_phos, calc['mineral']['status'], delta_color=delta_color)
            
            with col4:
                hgb = st.session_state['patient_data']['labs']['hemoglobin']
                delta_color = "normal" if 10.0 <= hgb <= 11.5 else "inverse"
                st.metric("Hemoglobin", f"{hgb} g/dL", calc['anemia']['status'], delta_color=delta_color)
            
            st.markdown("---")
            
            # Display full report
            st.text_area("Full Clinical Report", st.session_state['report_text'], height=600)
            
            # Download buttons
            col1, col2, col3 = st.columns([1, 1, 1])
            
            with col1:
                # Text download
                st.download_button(
                    label="📄 Download as Text",
                    data=st.session_state['report_text'],
                    file_name=f"dialysis_report_{st.session_state['patient_data']['mrn']}_{datetime.now().strftime('%Y%m%d')}.txt",
                    mime="text/plain"
                )
            
            with col2:
                # PDF download
                pdf_buffer = generate_pdf_report(
                    st.session_state['report_text'],
                    st.session_state['patient_data']['patient_name'],
                    st.session_state['patient_data']['mrn']
                )
                st.download_button(
                    label="📑 Download as PDF",
                    data=pdf_buffer,
                    file_name=f"dialysis_report_{st.session_state['patient_data']['mrn']}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
            
            with col3:
                # Email option (placeholder)
                if st.button("📧 Email Report", use_container_width=True):
                    st.info("📧 Email functionality coming soon! For now, download and email manually.")
        
        else:
            st.info("👈 Please enter patient data in the 'Data Entry' tab and click 'Generate Clinical Report' to see results here.")
            
            # Show sample report
            with st.expander("👁️ View Sample Report"):
                st.markdown("""
                ```
                ═══════════════════════════════════════════════════════
                    NEPHROLOGY CLINICAL ASSESSMENT REPORT
                ═══════════════════════════════════════════════════════
                
                Patient: Sample Patient (MRN: 12345)
                Date: February 10, 2025
                
                1. DIALYSIS ADEQUACY ASSESSMENT
                ✓ ADEQUATE - No changes needed
                
                Key Metrics:
                • Kt/V: 1.52 (Target: ≥1.4) ✓
                • URR: 67.6% (Target: ≥65%) ✓
                
                [Additional sections would appear here...]
                ```
                """)
    
    with tab3:
        st.header("About This Application")
        
        st.markdown("""
        ### 🎯 Purpose
        This AI-powered system assists nephrologists in generating comprehensive clinical assessment reports for dialysis patients. It automatically:
        
        - **Calculates** Kt/V, URR, and other key metrics
        - **Assesses** dialysis adequacy, mineral metabolism, anemia, and nutrition
        - **Generates** detailed clinical reports with specific recommendations
        - **References** KDOQI/KDIGO guidelines
        - **Exports** professional PDF reports
        - **Uses SI Units** (International System) for global compatibility
        
        ### 📐 Calculations Used
        
        **Kt/V (Daugirdas Second Generation Formula):**
        ```
        Kt/V = -ln(R - 0.008×t) + (4 - 3.5×R) × (UF/W)
        where R = post-urea/pre-urea, t = time, UF = ultrafiltration, W = weight
        ```
        
        **URR (Urea Reduction Ratio):**
        ```
        URR = (Pre-Urea - Post-Urea) / Pre-Urea × 100%
        ```
        
        **Ca×Phos Product (SI units):**
        ```
        Ca×Phos = Calcium (mmol/L) × Phosphorus (mmol/L)
        Target: <4.4 (mmol/L)²
        ```
        
        ### 🌍 SI Unit Reference Ranges
        
        **Dialysis Labs:**
        - Urea: 2.5-7.5 mmol/L (normal)
        - Pre-dialysis: typically 15-30 mmol/L
        
        **Mineral Metabolism:**
        - Calcium: 2.1-2.37 mmol/L (KDIGO target)
        - Phosphorus: 1.13-1.78 mmol/L (KDIGO target)
        - PTH: 15.9-31.8 pmol/L (target range)
        - Ca×Phos: <4.4 (mmol/L)²
        
        **Anemia:**
        - Hemoglobin: 100-115 g/L (target)
        - Ferritin: ≥200 µg/L (target)
        - TSAT: ≥20% (target)
        
        **Nutrition:**
        - Albumin: ≥38 g/L (target)
        - nPCR: 1.0-1.2 g/kg/day
        
        ### 📚 Guidelines Referenced
        
        - **KDOQI 2015** - Hemodialysis Adequacy
        - **KDIGO 2017** - CKD-MBD Management
        - **KDOQI 2020** - Anemia in CKD
        - **KDOQI/ASPEN 2020** - Nutrition in CKD
        
        ### 🔄 Unit Conversion Reference
        
        **Urea:**
        - mg/dL × 0.357 = mmol/L
        - mmol/L × 2.8 = mg/dL (as BUN)
        
        **Calcium:**
        - mg/dL × 0.25 = mmol/L
        - mmol/L × 4.0 = mg/dL
        
        **Phosphorus:**
        - mg/dL × 0.323 = mmol/L
        - mmol/L × 3.1 = mg/dL
        
        **PTH:**
        - pg/mL × 0.106 = pmol/L
        - pmol/L × 9.43 = pg/mL
        
        **Hemoglobin:**
        - g/dL × 10 = g/L
        - g/L ÷ 10 = g/dL
        
        **Albumin:**
        - g/dL × 10 = g/L
        - g/L ÷ 10 = g/dL
        
        ### ⚠️ Important Notes
        
        - This is a **clinical decision support tool**, not a replacement for clinical judgment
        - All recommendations should be reviewed by a qualified nephrologist
        - Patient-specific factors may require deviation from standard guidelines
        - For HIPAA compliance in production, ensure proper data encryption and BAA with AI provider
        - SI units are used throughout for international standardization
        
        ### 🔧 Technical Details
        
        **Built with:**
        - Python 3.x
        - Streamlit (Web Framework)
        - ReportLab (PDF Generation)
        - Pandas (Data Processing)
        
        **Future Enhancements:**
        - CSV/Excel batch upload
        - EMR integration (HL7/FHIR)
        - Historical trend analysis
        - Multi-patient dashboard
        - Email notification system
        - Mobile app version
        
        ### 📞 Support
        
        For questions or feature requests, contact your IT department or the development team.
        
        ---
        
        **Version:** 1.0.0 (SI Units)
        **Last Updated:** February 2025  
        **License:** For internal medical use only
        """)


if __name__ == "__main__":
    main()
