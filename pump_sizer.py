import streamlit as st
import math

# ==============================================================================
# --- PumpSizer Class (Copied from the previous script) ---
# ==============================================================================
class PumpSizer:
    """
    A class to perform sizing calculations for a centrifugal pump based on
    system parameters and fluid properties.

    It calculates Total Dynamic Head (TDH), power requirements, and Net
    Positive Suction Head Available (NPSHa).
    """

    # --- Heuristics and Standard Data ---
    PIPE_ROUGHNESS = {
        'commercial_steel': 0.000045,
        'stainless_steel': 0.000002,
        'pvc': 0.0000015,
        'cast_iron': 0.00026,
        'hdpe': 0.0000015,
    }
    FITTINGS_K_VALUES = {
        'elbow_90_std': 0.9,
        'elbow_90_long_radius': 0.6,
        'elbow_45_std': 0.4,
        'gate_valve_fully_open': 0.2,
        'ball_valve_fully_open': 0.1,
        'globe_valve_fully_open': 10.0,
        'check_valve_swing': 2.5,
        'tee_through_flow': 0.6,
        'tee_branch_flow': 1.8,
        'pipe_entrance_sharp': 0.5,
        'pipe_exit_sharp': 1.0,
    }
    STANDARD_MOTOR_KW = [
        0.37, 0.55, 0.75, 1.1, 1.5, 2.2, 3, 4, 5.5, 7.5, 11, 15, 18.5, 
        22, 30, 37, 45, 55, 75, 90, 110, 132, 160, 200, 250
    ]
    GRAVITY = 9.81  # m/s^2

    def __init__(self, flow_rate_m3_hr, fluid_density_kg_m3, fluid_viscosity_cP):
        self.flow_rate_m3_s = flow_rate_m3_hr / 3600.0
        self.density = fluid_density_kg_m3
        self.viscosity_Pa_s = fluid_viscosity_cP / 1000.0
        self.results = {}

    def _calculate_velocity(self, pipe_dia_mm):
        pipe_dia_m = pipe_dia_mm / 1000.0
        if pipe_dia_m == 0: return 0
        area = math.pi * (pipe_dia_m ** 2) / 4.0
        return self.flow_rate_m3_s / area

    def _calculate_reynolds(self, velocity, pipe_dia_mm):
        pipe_dia_m = pipe_dia_mm / 1000.0
        if self.viscosity_Pa_s == 0:
            return float('inf')
        return (self.density * velocity * pipe_dia_m) / self.viscosity_Pa_s

    def _calculate_friction_factor(self, reynolds, pipe_dia_mm, pipe_material):
        if reynolds < 2300:
            return 64 / reynolds if reynolds > 0 else 0
        pipe_dia_m = pipe_dia_mm / 1000.0
        epsilon = self.PIPE_ROUGHNESS.get(pipe_material, 0.000045)
        if pipe_dia_m == 0: return 0
        term1 = epsilon / (3.7 * pipe_dia_m)
        term2 = 5.74 / (reynolds ** 0.9)
        log_term = math.log10(term1 + term2)
        return 0.25 / (log_term ** 2)

    def calculate_tdh(self, suction_pipe_dia_mm, discharge_pipe_dia_mm, 
                        total_pipe_length_m, pipe_material, fittings,
                        elevation_change_m, source_pressure_barg, dest_pressure_barg):
        static_head = elevation_change_m
        source_pressure_pa = source_pressure_barg * 1e5
        dest_pressure_pa = dest_pressure_barg * 1e5
        pressure_head = (dest_pressure_pa - source_pressure_pa) / (self.density * self.GRAVITY)
        
        # Use discharge pipe for overall friction calculation
        velocity = self._calculate_velocity(discharge_pipe_dia_mm)
        reynolds = self._calculate_reynolds(velocity, discharge_pipe_dia_mm)
        friction_factor = self._calculate_friction_factor(reynolds, discharge_pipe_dia_mm, pipe_material)
        pipe_dia_m = discharge_pipe_dia_mm / 1000.0
        pipe_head_loss = friction_factor * (total_pipe_length_m / pipe_dia_m) * (velocity**2 / (2 * self.GRAVITY)) if pipe_dia_m > 0 else 0
        total_k = sum(self.FITTINGS_K_VALUES[key] * count for key, count in fittings.items() if count > 0)
        fittings_head_loss = total_k * (velocity**2 / (2 * self.GRAVITY))
        friction_head = pipe_head_loss + fittings_head_loss
        tdh = static_head + pressure_head + friction_head
        
        self.results.update({
            'tdh_m': tdh, 'static_head_m': static_head, 'pressure_head_m': pressure_head,
            'friction_head_m': friction_head, 'velocity_m_s': velocity, 'reynolds_number': reynolds
        })
        return tdh

    def calculate_power(self, tdh_m, pump_efficiency=0.75, motor_efficiency=0.90):
        hydraulic_power_W = self.flow_rate_m3_s * self.density * self.GRAVITY * tdh_m
        bhp_W = hydraulic_power_W / pump_efficiency if pump_efficiency > 0 else float('inf')
        motor_power_W = bhp_W / motor_efficiency if motor_efficiency > 0 else float('inf')
        motor_power_kW = motor_power_W / 1000.0
        recommended_motor_kW = next((size for size in self.STANDARD_MOTOR_KW if size >= motor_power_kW), self.STANDARD_MOTOR_KW[-1])

        self.results.update({
            'hydraulic_power_kW': hydraulic_power_W / 1000.0,
            'brake_horsepower_kW': bhp_W / 1000.0,
            'motor_power_required_kW': motor_power_kW,
            'recommended_motor_kW': recommended_motor_kW
        })
        return self.results
        
    def calculate_npsha(self, suction_pipe_dia_mm, suction_pipe_length_m, 
                        suction_pipe_material, suction_fittings, 
                        liquid_level_above_suction_m, suction_vessel_pressure_barg,
                        liquid_vapor_pressure_bar_abs):
        suction_vessel_pressure_pa_abs = (suction_vessel_pressure_barg * 1e5) + 101325
        pressure_head_at_source = suction_vessel_pressure_pa_abs / (self.density * self.GRAVITY)
        static_suction_head = liquid_level_above_suction_m
        vapor_pressure_pa_abs = liquid_vapor_pressure_bar_abs * 1e5
        vapor_pressure_head = vapor_pressure_pa_abs / (self.density * self.GRAVITY)
        
        velocity = self._calculate_velocity(suction_pipe_dia_mm)
        reynolds = self._calculate_reynolds(velocity, suction_pipe_dia_mm)
        friction_factor = self._calculate_friction_factor(reynolds, suction_pipe_dia_mm, suction_pipe_material)
        pipe_dia_m = suction_pipe_dia_mm / 1000.0
        pipe_loss = friction_factor * (suction_pipe_length_m / pipe_dia_m) * (velocity**2 / (2 * self.GRAVITY)) if pipe_dia_m > 0 else 0
        total_k = sum(self.FITTINGS_K_VALUES[key] * count for key, count in suction_fittings.items() if count > 0)
        fittings_loss = total_k * (velocity**2 / (2 * self.GRAVITY))
        total_suction_friction_head = pipe_loss + fittings_loss
        
        npsha = pressure_head_at_source + static_suction_head - vapor_pressure_head - total_suction_friction_head
        self.results['npsha_m'] = npsha
        return npsha

# ==============================================================================
# --- STREAMLIT APP UI AND LOGIC ---
# ==============================================================================

st.set_page_config(page_title="Centrifugal Pump Sizer", layout="wide")

st.title("Centrifugal Pump Sizing Calculator")
st.write("An interactive tool for process engineers to perform preliminary pump sizing calculations. All inputs can be adjusted in the sidebar.")

# --- SIDEBAR FOR USER INPUTS ---
st.sidebar.header("System & Process Inputs")

# --- Fluid & Process Inputs ---
st.sidebar.subheader("1. Fluid & Process")
flow_rate = st.sidebar.number_input("Flow Rate (m³/hr)", min_value=0.1, value=50.0, step=1.0)
density = st.sidebar.number_input("Fluid Density (kg/m³)", min_value=1.0, value=998.0, step=10.0)
viscosity = st.sidebar.number_input("Fluid Viscosity (cP)", min_value=0.1, value=1.0, step=0.1)
vapor_pressure = st.sidebar.number_input("Fluid Vapor Pressure (bar, absolute)", min_value=0.0, value=0.023, step=0.01, format="%.3f")

# --- System Geometry Inputs ---
st.sidebar.subheader("2. Piping & System Geometry")
source_pressure = st.sidebar.number_input("Source Vessel Pressure (barg)", value=0.0, step=0.1)
dest_pressure = st.sidebar.number_input("Destination Vessel Pressure (barg)", value=2.5, step=0.1)
elevation_change = st.sidebar.number_input("Elevation Change (m, dest - source)", value=15.0, step=0.5)
pipe_material = st.sidebar.selectbox("Pipe Material", options=list(PumpSizer.PIPE_ROUGHNESS.keys()), index=0)

st.sidebar.markdown("---")
# Suction Side
st.sidebar.markdown("**Suction Piping**")
suction_pipe_dia = st.sidebar.number_input("Suction Pipe Diameter (mm)", min_value=1.0, value=100.0, step=1.0)
suction_pipe_len = st.sidebar.number_input("Suction Pipe Length (m)", min_value=0.0, value=10.0, step=1.0)

# Discharge Side
st.sidebar.markdown("**Discharge Piping**")
discharge_pipe_dia = st.sidebar.number_input("Discharge Pipe Diameter (mm)", min_value=1.0, value=75.0, step=1.0)
discharge_pipe_len = st.sidebar.number_input("Discharge Pipe Length (m)", min_value=0.0, value=110.0, step=1.0)
total_pipe_len = suction_pipe_len + discharge_pipe_len

# Fittings Input
with st.sidebar.expander("Enter Pipe Fittings (Total System)"):
    fittings_total = {}
    for name, k in PumpSizer.FITTINGS_K_VALUES.items():
        # Default values from the original example
        default_val = 0
        if name == 'pipe_entrance_sharp': default_val = 1
        if name == 'elbow_90_long_radius': default_val = 5
        if name == 'gate_valve_fully_open': default_val = 2
        if name == 'pipe_exit_sharp': default_val = 1
        
        fittings_total[name] = st.number_input(f"Count of '{name.replace('_',' ').title()}'", min_value=0, value=default_val, key=f"total_{name}")

# --- NPSH Inputs ---
st.sidebar.subheader("3. NPSH Calculation")
liquid_level = st.sidebar.number_input("Liquid Level Above Pump Suction (m)", value=2.0, step=0.1)

with st.sidebar.expander("Enter Suction Line-Only Fittings"):
    fittings_suction = {}
    for name, k in PumpSizer.FITTINGS_K_VALUES.items():
         # Default values from the original example
        default_val = 0
        if name == 'pipe_entrance_sharp': default_val = 1
        if name == 'elbow_90_long_radius': default_val = 1
        if name == 'gate_valve_fully_open': default_val = 1

        fittings_suction[name] = st.number_input(f"Count of '{name.replace('_',' ').title()}'", min_value=0, value=default_val, key=f"suction_{name}")

# --- Efficiency Inputs ---
st.sidebar.subheader("4. Efficiencies")
pump_eff = st.sidebar.slider("Estimated Pump Efficiency", 0.1, 1.0, 0.75)
motor_eff = st.sidebar.slider("Estimated Motor Efficiency", 0.1, 1.0, 0.90)

# --- Calculation Trigger ---
if st.sidebar.button("Calculate Pump Size", type="primary"):

    # --- 1. Initialize and Calculate ---
    pump_calc = PumpSizer(flow_rate, density, viscosity)

    tdh = pump_calc.calculate_tdh(
        suction_pipe_dia_mm=suction_pipe_dia,
        discharge_pipe_dia_mm=discharge_pipe_dia,
        total_pipe_length_m=total_pipe_len,
        pipe_material=pipe_material,
        fittings=fittings_total,
        elevation_change_m=elevation_change,
        source_pressure_barg=source_pressure,
        dest_pressure_barg=dest_pressure
    )

    pump_calc.calculate_power(tdh, pump_eff, motor_eff)

    npsha = pump_calc.calculate_npsha(
        suction_pipe_dia_mm=suction_pipe_dia,
        suction_pipe_length_m=suction_pipe_len,
        suction_pipe_material=pipe_material,
        suction_fittings=fittings_suction,
        liquid_level_above_suction_m=liquid_level,
        suction_vessel_pressure_barg=source_pressure,
        liquid_vapor_pressure_bar_abs=vapor_pressure
    )

    results = pump_calc.results

    # --- 2. Display Results ---
    st.header("Calculation Results")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Dynamic Head (TDH)", f"{results.get('tdh_m', 0):.2f} m")
    col2.metric("Recommended Motor Size", f"{results.get('recommended_motor_kW', 0):.2f} kW")
    col3.metric("NPSH Available (NPSHa)", f"{results.get('npsha_m', 0):.2f} m")

    # NPSH Recommendation
    if npsha < 1.0:
        st.error(f"**CRITICAL RISK:** NPSHa is {npsha:.2f} m. High probability of cavitation. System redesign is required.")
    elif npsha < 3.0:
        st.warning(f"**CAUTION:** NPSHa is {npsha:.2f} m. This is low. Carefully check pump's NPSHr and ensure a safety margin of at least 0.5-1.0m.")
    else:
        st.success(f"**OK:** NPSHa is {npsha:.2f} m. This is a healthy value. Ensure it is greater than the selected pump's NPSHr plus a safety margin.")


    with st.expander("Show Detailed Calculation Breakdown"):
        st.subheader("Head Calculation Details")
        c1, c2, c3 = st.columns(3)
        c1.metric("Static Head", f"{results.get('static_head_m', 0):.2f} m")
        c2.metric("Pressure Head", f"{results.get('pressure_head_m', 0):.2f} m")
        c3.metric("Friction Head", f"{results.get('friction_head_m', 0):.2f} m")
        
        st.subheader("Power Calculation Details")
        c1, c2, c3 = st.columns(3)
        c1.metric("Hydraulic Power", f"{results.get('hydraulic_power_kW', 0):.2f} kW")
        c2.metric("Brake Horsepower (Shaft)", f"{results.get('brake_horsepower_kW', 0):.2f} kW")
        c3.metric("Motor Power Required", f"{results.get('motor_power_required_kW', 0):.2f} kW")
        
        st.subheader("Flow Characteristics")
        st.write(f"**Velocity in Discharge Pipe:** {results.get('velocity_m_s', 0):.2f} m/s")
        st.write(f"**Reynolds Number:** {results.get('reynolds_number', 0):.0f}")

else:
    st.info("Adjust the parameters in the sidebar and click 'Calculate Pump Size' to see the results.")

