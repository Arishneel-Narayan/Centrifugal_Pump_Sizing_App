import streamlit as st
import math
from datetime import datetime
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# ==============================================================================
# --- PDF Report Generation (Using ReportLab) ---
# ==============================================================================
def create_pdf_report(inputs, results, flow_regime):
    """Generates a PDF report using ReportLab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    styles = getSampleStyleSheet()
    
    Story = []

    # --- Header ---
    title = Paragraph("Centrifugal Pump Sizing Report", styles['h1'])
    timestamp = Paragraph(f'Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', styles['Normal'])
    Story.append(title)
    Story.append(timestamp)
    Story.append(Spacer(1, 0.25*inch))

    # --- Helper function for creating sections ---
    def create_section(title_text, data_dict):
        Story.append(Paragraph(title_text, styles['h2']))
        Story.append(Spacer(1, 0.1*inch))
        
        # Convert dict to list of lists for the table
        data_list = [[key, value] for key, value in data_dict.items()]
        
        table = Table(data_list, colWidths=[2.5*inch, 3.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (0,-1), colors.lightgrey),
            ('TEXTCOLOR',(0,0),(-1,-1),colors.black),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 1, colors.black)
        ]))
        Story.append(table)
        Story.append(Spacer(1, 0.25*inch))

    # --- 1. Input Parameters ---
    input_data = {
        "Fluid Template": inputs['fluid_template'],
        "Flow Rate (m³/hr)": f"{inputs['flow_rate']:.2f}",
        "Fluid Density (kg/m³)": f"{inputs['density']:.2f}",
        "Fluid Viscosity (cP)": f"{inputs['viscosity']:.2f}",
        "Vapor Pressure (kPa, abs)": f"{inputs['vapor_pressure']:.2f}",
        "Source Pressure (kPa, gauge)": f"{inputs['source_pressure']:.2f}",
        "Destination Pressure (kPa, gauge)": f"{inputs['dest_pressure']:.2f}",
        "Elevation Change (m)": f"{inputs['elevation_change']:.2f}",
        "Pipe Material": inputs['pipe_material'],
        "Suction Pipe Dia. (mm)": f"{inputs['suction_pipe_dia']:.2f}",
        "Suction Pipe Len. (m)": f"{inputs['suction_pipe_len']:.2f}",
        "Discharge Pipe Dia. (mm)": f"{inputs['discharge_pipe_dia']:.2f}",
        "Discharge Pipe Len. (m)": f"{inputs['discharge_pipe_len']:.2f}",
        "Liquid Level Above Suction (m)": f"{inputs['liquid_level']:.2f}",
        "Pump Efficiency": f"{inputs['pump_eff']:.2%}",
        "Motor Efficiency": f"{inputs['motor_eff']:.2%}"
    }
    create_section("1. Input Parameters", input_data)

    # --- 2. Key Results ---
    results_data = {
        "Total Dynamic Head (TDH)": f"{results.get('tdh_m', 0):.2f} m",
        "Recommended Motor Size": f"{results.get('recommended_motor_kW', 0):.2f} kW",
        "NPSH Available (NPSHa)": f"{results.get('npsha_m', 0):.2f} m",
    }
    create_section("2. Key Results", results_data)

    # --- 3. Detailed Breakdown ---
    details_data = {
        "Static Head": f"{results.get('static_head_m', 0):.2f} m",
        "Pressure Head": f"{results.get('pressure_head_m', 0):.2f} m",
        "Friction Head": f"{results.get('friction_head_m', 0):.2f} m",
        "Hydraulic Power": f"{results.get('hydraulic_power_kW', 0):.2f} kW",
        "Brake Horsepower (Shaft)": f"{results.get('brake_horsepower_kW', 0):.2f} kW",
        "Motor Power Required": f"{results.get('motor_power_required_kW', 0):.2f} kW",
        "Velocity (Discharge Pipe)": f"{results.get('velocity_m_s', 0):.2f} m/s",
        "Reynolds Number": f"{results.get('reynolds_number', 0):.0f} ({flow_regime})",
    }
    create_section("3. Detailed Calculation Breakdown", details_data)
    
    doc.build(Story)
    buffer.seek(0)
    return buffer


# ==============================================================================
# --- PumpSizer Class ---
# ==============================================================================
class PumpSizer:
    PIPE_ROUGHNESS = {'stainless_steel': 2e-06, 'commercial_steel': 4.5e-05, 'pvc': 1.5e-06, 'cast_iron': 0.00026, 'hdpe': 1.5e-06}
    FITTINGS_K_VALUES = {'elbow_90_std': 0.9, 'elbow_90_long_radius': 0.6, 'elbow_45_std': 0.4, 'gate_valve_fully_open': 0.2, 'ball_valve_fully_open': 0.1, 'globe_valve_fully_open': 10.0, 'check_valve_swing': 2.5, 'tee_through_flow': 0.6, 'tee_branch_flow': 1.8, 'pipe_entrance_sharp': 0.5, 'pipe_exit_sharp': 1.0}
    STANDARD_MOTOR_KW = [0.37, 0.55, 0.75, 1.1, 1.5, 2.2, 3, 4, 5.5, 7.5, 11, 15, 18.5, 22, 30, 37, 45, 55, 75, 90, 110, 132, 160, 200, 250]
    GRAVITY = 9.81
    def __init__(self, flow_rate_m3_hr, fluid_density_kg_m3, fluid_viscosity_cP):
        self.flow_rate_m3_s = flow_rate_m3_hr / 3600.0
        self.density = fluid_density_kg_m3 if fluid_density_kg_m3 > 0 else 1
        self.viscosity_Pa_s = fluid_viscosity_cP / 1000.0
        self.results = {}
    def _calculate_velocity(self, pipe_dia_mm):
        pipe_dia_m = pipe_dia_mm / 1000.0
        if pipe_dia_m == 0: return 0
        area = math.pi * (pipe_dia_m ** 2) / 4.0
        return self.flow_rate_m3_s / area
    def _calculate_reynolds(self, velocity, pipe_dia_mm):
        pipe_dia_m = pipe_dia_mm / 1000.0
        if self.viscosity_Pa_s == 0: return float('inf')
        return (self.density * velocity * pipe_dia_m) / self.viscosity_Pa_s
    def _calculate_friction_factor(self, reynolds, pipe_dia_mm, pipe_material):
        if reynolds < 2300: return 64 / reynolds if reynolds > 0 else 0
        pipe_dia_m = pipe_dia_mm / 1000.0
        epsilon = self.PIPE_ROUGHNESS.get(pipe_material, 4.5e-05)
        if pipe_dia_m == 0: return 0
        term1 = epsilon / (3.7 * pipe_dia_m)
        term2 = 5.74 / (reynolds ** 0.9)
        if (term1 + term2) <= 0: return 0
        log_term = math.log10(term1 + term2)
        return 0.25 / (log_term ** 2)
    def calculate_tdh(self, suction_pipe_dia_mm, discharge_pipe_dia_mm, total_pipe_length_m, pipe_material, fittings, elevation_change_m, source_pressure_kpa_g, dest_pressure_kpa_g):
        static_head = elevation_change_m
        pressure_head = ((dest_pressure_kpa_g - source_pressure_kpa_g) * 1000) / (self.density * self.GRAVITY)
        velocity = self._calculate_velocity(discharge_pipe_dia_mm)
        reynolds = self._calculate_reynolds(velocity, discharge_pipe_dia_mm)
        friction_factor = self._calculate_friction_factor(reynolds, discharge_pipe_dia_mm, pipe_material)
        pipe_dia_m = discharge_pipe_dia_mm / 1000.0
        pipe_head_loss = friction_factor * (total_pipe_length_m / pipe_dia_m) * (velocity ** 2 / (2 * self.GRAVITY)) if pipe_dia_m > 0 else 0
        total_k = sum(self.FITTINGS_K_VALUES[key] * count for key, count in fittings.items() if count > 0)
        fittings_head_loss = total_k * (velocity ** 2 / (2 * self.GRAVITY))
        friction_head = pipe_head_loss + fittings_head_loss
        tdh = static_head + pressure_head + friction_head
        self.results.update({'tdh_m': tdh, 'static_head_m': static_head, 'pressure_head_m': pressure_head, 'friction_head_m': friction_head, 'velocity_m_s': velocity, 'reynolds_number': reynolds})
        return tdh
    def calculate_power(self, tdh_m, pump_efficiency=0.75, motor_efficiency=0.9):
        hydraulic_power_W = self.flow_rate_m3_s * self.density * self.GRAVITY * tdh_m
        bhp_W = hydraulic_power_W / pump_efficiency if pump_efficiency > 0 else float('inf')
        motor_power_W = bhp_W / motor_efficiency if motor_efficiency > 0 else float('inf')
        motor_power_kW = motor_power_W / 1000.0
        recommended_motor_kW = next((size for size in self.STANDARD_MOTOR_KW if size >= motor_power_kW), self.STANDARD_MOTOR_KW[-1])
        self.results.update({'hydraulic_power_kW': motor_power_W / 1000.0 / motor_efficiency if motor_efficiency > 0 else float('inf'), 'brake_horsepower_kW': bhp_W / 1000.0, 'motor_power_required_kW': motor_power_kW, 'recommended_motor_kW': recommended_motor_kW})
        return self.results
    def calculate_npsha(self, suction_pipe_dia_mm, suction_pipe_length_m, suction_pipe_material, suction_fittings, liquid_level_above_suction_m, suction_vessel_pressure_kpa_g, liquid_vapor_pressure_kpa_abs):
        pressure_head_at_source = ((suction_vessel_pressure_kpa_g * 1000) + 101325) / (self.density * self.GRAVITY)
        vapor_pressure_head = (liquid_vapor_pressure_kpa_abs * 1000) / (self.density * self.GRAVITY)
        velocity = self._calculate_velocity(suction_pipe_dia_mm)
        reynolds = self._calculate_reynolds(velocity, suction_pipe_dia_mm)
        friction_factor = self._calculate_friction_factor(reynolds, suction_pipe_dia_mm, suction_pipe_material)
        pipe_dia_m = suction_pipe_dia_mm / 1000.0
        pipe_loss = friction_factor * (suction_pipe_length_m / pipe_dia_m) * (velocity ** 2 / (2 * self.GRAVITY)) if pipe_dia_m > 0 else 0
        total_k = sum(self.FITTINGS_K_VALUES[key] * count for key, count in suction_fittings.items() if count > 0)
        fittings_loss = total_k * (velocity ** 2 / (2 * self.GRAVITY))
        total_suction_friction_head = pipe_loss + fittings_loss
        npsha = pressure_head_at_source + liquid_level_above_suction_m - vapor_pressure_head - total_suction_friction_head
        self.results['npsha_m'] = npsha
        return npsha

# ==============================================================================
# --- STREAMLIT APP UI AND LOGIC ---
# ==============================================================================

st.set_page_config(page_title="Centrifugal Pump Sizer", layout="wide")

st.title("Centrifugal Pump Sizing Calculator")
st.write("A simplified tool for sizing pumps in food-grade applications. All inputs are in the top section below.")
st.markdown("---")

# --- Fluid Templates ---
FLUID_TEMPLATES = {
    "Custom": {"density": 1000.0, "viscosity": 1.0, "vapor_pressure": 2.3},
    "Water (20°C)": {"density": 998.2, "viscosity": 1.0, "vapor_pressure": 2.3},
    "Vegetable Oil (40°C)": {"density": 910.0, "viscosity": 30.0, "vapor_pressure": 0.01},
}
if 'fluid' not in st.session_state: st.session_state.fluid = "Water (20°C)"
if 'density' not in st.session_state: st.session_state.density = FLUID_TEMPLATES[st.session_state.fluid]['density']
if 'viscosity' not in st.session_state: st.session_state.viscosity = FLUID_TEMPLATES[st.session_state.fluid]['viscosity']
if 'vapor_pressure' not in st.session_state: st.session_state.vapor_pressure = FLUID_TEMPLATES[st.session_state.fluid]['vapor_pressure']

def update_fluid_properties():
    selected_fluid = st.session_state.fluid_template
    if selected_fluid != "Custom":
        st.session_state.density = FLUID_TEMPLATES[selected_fluid]['density']
        st.session_state.viscosity = FLUID_TEMPLATES[selected_fluid]['viscosity']
        st.session_state.vapor_pressure = FLUID_TEMPLATES[selected_fluid]['vapor_pressure']

st.header("System & Process Inputs")
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.subheader("1. Fluid & Process")
    st.selectbox("Fluid Template", options=list(FLUID_TEMPLATES.keys()), key='fluid_template', on_change=update_fluid_properties, help="Select a fluid template to auto-fill properties, or choose 'Custom'.")
    flow_rate = st.number_input("Flow Rate (m³/hr)", 0.1, value=50.0, step=1.0, help="The volume of liquid you need to move per hour.")
    density = st.number_input("Fluid Density (kg/m³)", 1.0, key='density', step=10.0, help="The mass of the fluid per unit volume. Water is approx. 1000 kg/m³.")
    viscosity = st.number_input("Fluid Viscosity (cP)", 0.1, key='viscosity', step=0.1, help="The fluid's resistance to flow. Water is 1 cP at 20°C.")
    vapor_pressure = st.number_input("Fluid Vapor Pressure (kPa, abs)", 0.0, key='vapor_pressure', format="%.2f", help="The pressure at which the liquid will start to boil at the operating temperature.")
with col2:
    st.subheader("2. System Geometry")
    source_pressure = st.number_input("Source Pressure (kPa, gauge)", value=0.0, step=5.0, help="The pressure in the tank the fluid is being pumped FROM.")
    dest_pressure = st.number_input("Destination Pressure (kPa, gauge)", value=250.0, step=5.0, help="The pressure in the tank the fluid is being pumped TO.")
    elevation_change = st.number_input("Elevation Change (m)", value=15.0, step=0.5, help="The vertical height difference between the destination and source liquid surfaces.")
    pipe_material = st.selectbox("Pipe Material", options=list(PumpSizer.PIPE_ROUGHNESS.keys()), index=0, help="Material of the piping. Stainless steel is typical for food applications.")
with col3:
    st.subheader("3. Piping Details")
    suction_pipe_dia = st.number_input("Suction Pipe Dia. (mm)", 1.0, value=100.0, step=1.0, help="Inner diameter of the pipe BEFORE the pump.")
    suction_pipe_len = st.number_input("Suction Pipe Len. (m)", 0.0, value=10.0, step=1.0, help="Length of the pipe on the suction side only.")
    discharge_pipe_dia = st.number_input("Discharge Pipe Dia. (mm)", 1.0, value=75.0, step=1.0, help="Inner diameter of the pipe AFTER the pump.")
    discharge_pipe_len = st.number_input("Discharge Pipe Len. (m)", 0.0, value=110.0, step=1.0, help="Length of the pipe on the discharge side only.")
    total_pipe_len = suction_pipe_len + discharge_pipe_len
with col4:
    st.subheader("4. NPSH & Efficiency")
    liquid_level = st.number_input("Liquid Level Above Suction (m)", value=2.0, step=0.1, help="The vertical height of liquid in the source tank above the pump's inlet.")
    pump_eff = st.slider("Pump Efficiency", 0.1, 1.0, 0.75, help="How efficiently the pump transfers energy to the fluid. Typically 70-85%.")
    motor_eff = st.slider("Motor Efficiency", 0.1, 1.0, 0.90, help="How efficiently the motor converts electrical to shaft power. Typically 90-95%.")

fit_col1, fit_col2 = st.columns(2)
with fit_col1:
    with st.expander("Enter Total System Pipe Fittings"):
        fittings_total = {name: st.number_input(f"Count of '{name.replace('_',' ').title()}'", 0, value=0, key=f"total_{name}", help="Total number of this fitting in the entire system.") for name in PumpSizer.FITTINGS_K_VALUES}
with fit_col2:
    with st.expander("Enter Suction Line-Only Fittings"):
        fittings_suction = {name: st.number_input(f"Count of '{name.replace('_',' ').title()}'", 0, value=0, key=f"suction_{name}", help="Number of this fitting on the SUCTION side ONLY.") for name in PumpSizer.FITTINGS_K_VALUES}

st.markdown("---")

if 'results' not in st.session_state:
    st.session_state.results = None

if st.button("Calculate Pump Size", type="primary", use_container_width=True):
    pump_calc = PumpSizer(flow_rate, density, viscosity)
    tdh = pump_calc.calculate_tdh(suction_pipe_dia, discharge_pipe_dia, total_pipe_len, pipe_material, fittings_total, elevation_change, source_pressure, dest_pressure)
    pump_calc.calculate_power(tdh, pump_eff, motor_eff)
    npsha = pump_calc.calculate_npsha(suction_pipe_dia, suction_pipe_len, pipe_material, fittings_suction, liquid_level, source_pressure, vapor_pressure)
    st.session_state.results = pump_calc.results
    st.session_state.inputs = { 'fluid_template': st.session_state.fluid_template, 'flow_rate': flow_rate, 'density': density, 'viscosity': viscosity, 'vapor_pressure': vapor_pressure, 'source_pressure': source_pressure, 'dest_pressure': dest_pressure, 'elevation_change': elevation_change, 'pipe_material': pipe_material, 'suction_pipe_dia': suction_pipe_dia, 'suction_pipe_len': suction_pipe_len, 'discharge_pipe_dia': discharge_pipe_dia, 'discharge_pipe_len': discharge_pipe_len, 'liquid_level': liquid_level, 'pump_eff': pump_eff, 'motor_eff': motor_eff }

if st.session_state.results:
    results = st.session_state.results
    st.header("Calculation Results")
    res_col1, res_col2, res_col3 = st.columns(3)
    res_col1.metric("Total Dynamic Head (TDH)", f"{results.get('tdh_m', 0):.2f} m", help="The total pressure the pump must generate, expressed as fluid height.")
    res_col2.metric("Recommended Motor Size", f"{results.get('recommended_motor_kW', 0):.2f} kW", help="The standard motor size required to run the pump under these conditions.")
    res_col3.metric("NPSH Available (NPSHa)", f"{results.get('npsha_m', 0):.2f} m", help="The pressure margin at the pump inlet available to prevent cavitation.")
    
    npsha = results.get('npsha_m', 0)
    if npsha < 1.5: st.error(f"**CRITICAL RISK:** NPSHa is {npsha:.2f} m. High probability of cavitation. System redesign is required.")
    elif npsha < 3.0: st.warning(f"**CAUTION:** NPSHa is {npsha:.2f} m. This is low. Carefully check the pump's required NPSH (NPSHr) and ensure a safety margin of at least 1.0m.")
    else: st.success(f"**OK:** NPSHa is {npsha:.2f} m. This is a healthy value. Ensure it is greater than the selected pump's NPSHr plus a safety margin.")
    
    with st.expander("Show Detailed Calculation Breakdown"):
        st.subheader("Head Calculation Details")
        head_c1, head_c2, head_c3 = st.columns(3)
        head_c1.metric("Static Head", f"{results.get('static_head_m', 0):.2f} m")
        head_c2.metric("Pressure Head", f"{results.get('pressure_head_m', 0):.2f} m")
        head_c3.metric("Friction Head", f"{results.get('friction_head_m', 0):.2f} m")
        st.subheader("Power Calculation Details")
        power_c1, power_c2, power_c3 = st.columns(3)
        power_c1.metric("Hydraulic Power", f"{results.get('hydraulic_power_kW', 0):.2f} kW")
        power_c2.metric("Brake Horsepower (Shaft)", f"{results.get('brake_horsepower_kW', 0):.2f} kW")
        power_c3.metric("Motor Power Required", f"{results.get('motor_power_required_kW', 0):.2f} kW")
        st.subheader("Flow Characteristics")
        reynolds_val = results.get('reynolds_number', 0)
        flow_regime = "Laminar" if reynolds_val < 2300 else "Transitional" if reynolds_val <= 4000 else "Turbulent"
        st.write(f"**Velocity in Discharge Pipe:** {results.get('velocity_m_s', 0):.2f} m/s")
        st.write(f"**Reynolds Number:** {reynolds_val:.0f}  ({flow_regime} Flow)")
    
    # --- PDF Download Button ---
    st.markdown("---")
    pdf_data = create_pdf_report(st.session_state.inputs, results, flow_regime)
    st.download_button(
        label="Download Report as PDF",
        data=pdf_data,
        file_name=f"pump_sizing_report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime='application/pdf',
        use_container_width=True
    )
else:
    st.info("Adjust the parameters in the top section and click the 'Calculate Pump Size' button to see the results.")
