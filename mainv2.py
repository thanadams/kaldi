from tkinter import *
from tkinter import filedialog
import csv
import time
import datetime
from threading import Thread
import os
import collections
import sys
from tkinter import simpledialog

# Import for Matplotlib graph
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Import raspberry pi specific libraries
import RPi.GPIO as GPIO
from yoctopuce.yocto_api import *
from yoctopuce.yocto_temperature import *
from yoctopuce.yocto_relay import *

# --- TRON Theme Colors ---
TRON_BLACK = "#0D0208"
TRON_CYAN = "#00A9E0"
TRON_MAGENTA = "#DA00FF"
TRON_WHITE = "#FFFFFF"
TRON_GRID = "#333333"
TRON_ROR = "#FF8000" # Orange for RoR
TRON_HEAT_POWER = "#FF4444" # CHANGED: Less intense Neon Crimson for Heat Power
TRON_AIR_POWER = "#00FFFF" # Cyan for Air Power (New - TRON_CYAN is used for Bean Temp)
# --- End Theme ---

# --- Class to redirect stdout to the GUI console ---
class TextRedirector(object):
    def __init__(self, widget):
        self.widget = widget

    def write(self, str):
        self.widget.configure(state='normal')
        self.widget.insert('end', str)
        self.widget.see('end') # Auto-scroll
        self.widget.configure(state='disabled')

    def flush(self):
        pass # Required for stdout redirection

# Configure the temp sensor
errmsg = YRefParam()
if YAPI.RegisterHub("127.0.0.1", errmsg) != YAPI.SUCCESS:
    sys.exit("init error" + errmsg.value)

# Per user feedback, sensor1 ('...temperature1') is the Bean Mass probe
# and sensor2 ('...temperature2') is the Inlet Air probe.
sensor1 = YTemperature.FindTemperature('THRMCPL1-57DE2.temperature1') # Bean Mass
sensor2 = YTemperature.FindTemperature('THRMCPL1-57DE2.temperature2') # Inlet Air

if not (sensor1.isOnline() and sensor2.isOnline()):
    sys.exit('Error: Thermocouple sensors not found. Please check connections.')

# this is for the timer state
state = False

# Variables to hold the after() job IDs for clean shutdown
after_id_update_graph = None  # Removed, merging functionality
after_id_update_temp_power_graph = None # Renamed to new combined ID
after_id_update_timeText = None
after_id_poll_sensors = None
after_id_poll_display = None
after_id_auto_mark_start = None # Removed auto-start logic

# Using deque for memory efficiency, stores the last 10 minutes of data (1200 samples at 2 samples/sec)
# Data stored: [ch1_bt, ch2_inlet_air, air_power, heat_power, timetosend]
# The 6th element (index 5) is the elapsed time in seconds from roast start.
temps = collections.deque(maxlen=1200) 
ror_history = collections.deque(maxlen=600)

# RENAMED: This deque stores the smoothed BT history used ONLY for the RoR derivative calculation
smoothed_bt_ror_calc = collections.deque(maxlen=1200) 
# NEW: Deques for smoothed data that will be plotted on the Temp/Power graph
smoothed_bt_plot = collections.deque(maxlen=1200)
smoothed_ia_plot = collections.deque(maxlen=1200)

intervals = []
roast_events = []
start = True
profile = False

# Variables for accurate timekeeping
roast_start_time = 0
last_elapsed_time = 0

heat_upper_bound = 100
blower_upper_bound = 100

air_now = 0
heat_now = 0

roast_name = ""
# Reassigned to hold the single triple-axis figure and axes
fig = None 
ax1 = None 
ax2 = None
ax3 = None # NEW: Tertiary axis for RoR
profile_running = False

# Variables to store the last displayed temp value for 1-degree update check
last_displayed_bt = 0
last_displayed_ia = 0

# NEW GLOBAL VARIABLE: Tracks the time of the "First Crack" event
first_crack_time = 0


# --- GUI SETUP ---
gui = Tk()
gui.title("KALDI Roaster Control")
# CHANGED: Increased window size for better spacing
gui.geometry("700x900+30+30") 
gui.configure(bg=TRON_BLACK)

# Create frames for swapping between startup and main UI
startup_frame = Frame(gui, bg=TRON_BLACK)
main_frame = Frame(gui, bg=TRON_BLACK)

# --- Tkinter Variables (MOVED StringVar INITIALIZATION HERE) ---
bpwmdisp = StringVar()
bpwmdisp.set(air_now)
hpwmdisp = StringVar()
hpwmdisp.set(heat_now)

# Initialize StringVar objects before using them
t1disp = StringVar()
t2disp = StringVar()

ch1_val = round(sensor1.get_currentValue())
ch2_val = round(sensor2.get_currentValue())

# Now safely set their initial values
t1disp.set(ch1_val)
t2disp.set(ch2_val)

profiledisplayname = StringVar()
profiledisplayname.set('none')

# Variable for the configurable RoR time window
ror_time_window = IntVar()
# FIX: Reduced rolling average window for plotting from 5s to 3s for higher responsiveness
ror_time_window.set(3) 

# --- NEW FUNCTION FOR TRIPLE-AXIS GRAPH ---
def create_triple_axis_graph_window():
    """Creates a single window for the combined Temp/Power/RoR graph with three axes."""
    global fig, ax1, ax2, ax3
    graph_window = Toplevel(gui)
    graph_window.wm_title("Combined Roast Curve (Temp, Power, RoR)")
    # Adjusted position to be easily visible
    graph_window.geometry("1000x750+750+30") # Adjusted starting X position for wider main window
    graph_window.configure(bg=TRON_BLACK)

    fig = plt.Figure(figsize=(9, 7), dpi=100)
    fig.patch.set_facecolor(TRON_BLACK)
    
    # 1. Primary Axis (Left) - Temperatures
    ax1 = fig.add_subplot(111)
    ax1.set_facecolor(TRON_BLACK)
    
    # 2. Secondary Axis (Right) - Power Levels
    ax2 = ax1.twinx() 
    
    # 3. Tertiary Axis (Displaced Right) - RoR
    # Share the x-axis with ax1, and offset it outward from ax2
    ax3 = ax1.twinx()
    # Move the spine (border) for ax3 60 pixels outward
    ax3.spines['right'].set_position(('outward', 60))
    ax3.spines['right'].set_visible(True) # Ensure the spine is visible
    
    canvas = FigureCanvasTkAgg(fig, master=graph_window)
    canvas.get_tk_widget().pack(side=TOP, fill=BOTH, expand=1)
    canvas._tkcanvas.pack(side=TOP, fill=BOTH, expand=1)

    return ax1, ax2, ax3, canvas

def update_combined_graph(ax1, ax2, ax3, canvas):
    """Clears and redraws the combined Temp/Power/RoR graph."""
    global after_id_update_temp_power_graph
    
    ax1.clear()
    ax2.clear()
    ax3.clear() # Clear all three axes

    max_data_time = 0
    
    # --- Guard against plotting before roast start time is set ---
    if roast_start_time == 0 or len(smoothed_bt_plot) < 2:
        # If not running or not enough data, just set initial X-limits and stop plotting
        ax1.set_xlim(left=0, right=60)
        ax1.set_title("Combined Roast Curve: Temp, Power, and RoR (Waiting for START)", color=TRON_WHITE)
        ax1.set_xlabel("Time (seconds)", color=TRON_WHITE)
        ax1.set_ylabel("Temperature (°F)", color=TRON_CYAN)
        
        # Ensure secondary axes are configured even when empty
        ax2.set_ylim(0, 100)
        ax2.set_ylabel("Power Level (%)", color=TRON_WHITE)
        ax3.set_ylim(0, 150)
        ax3.set_ylabel("RoR (°F/min)", color=TRON_ROR)

        canvas.draw()
        after_id_update_temp_power_graph = gui.after(1000, update_combined_graph, ax1, ax2, ax3, canvas)
        return
    
    # --- Data Preparation (Only runs if roast_start_time > 0) ---
    
    smoothed_bt = list(smoothed_bt_plot)
    smoothed_ia = list(smoothed_ia_plot)
    num_smoothed_points = len(smoothed_bt_plot)
    
    temps_list = list(temps)
    all_data_points = temps_list[-num_smoothed_points:]
    
    # FIX: Get ELAPSED time directly from the 6th element (index 5) of the `temps` deque
    # This guarantees time alignment regardless of when logging started.
    x_times_elapsed = [d[5] for d in all_data_points]
    
    # Get powers corresponding to the smoothed points
    air_powers = [d[2] for d in all_data_points]
    heat_powers = [d[3] for d in all_data_points]
    
    # Calculate max time for setting x-limit
    if x_times_elapsed:
        max_data_time = x_times_elapsed[-1]
    
    # RoR history (sampled once per second)
    ror_data = list(ror_history) 
    rors = [r for t, r in ror_data]
    
    # RoR times are stored as elapsed time
    ror_times_elapsed = [t for t, r in ror_data]
    
    # The line will now naturally start at its first calculated point (at >= 30 seconds).

    # --- Plotting ---
    
    # 1. Temperatures (ax1 - Left Axis)
    ax1.plot(x_times_elapsed, smoothed_bt, color=TRON_CYAN, label='Bean Temp (°F)')
    ax1.plot(x_times_elapsed, smoothed_ia, color=TRON_MAGENTA, label='Inlet Temp (°F)')
    
    # 2. Power Levels (ax2 - Right Axis 1)
    ax2.plot(x_times_elapsed, air_powers, color=TRON_AIR_POWER, linestyle='--', label='Air Power (%)')
    ax2.plot(x_times_elapsed, heat_powers, color=TRON_HEAT_POWER, linestyle=':', label='Heat Power (%)')

    # 3. RoR (ax3 - Right Axis 2, Displaced)
    if rors:
        # CRITICAL: Plot RoR vs ELAPSED time
        ax3.plot(ror_times_elapsed, rors, color=TRON_ROR, marker='.', linestyle='-', markersize=2, label='RoR (°F/min)')
    
    
    # --- Axis Configuration ---
    
    # AX1 (Temperatures)
    ax1.set_title("Combined Roast Curve: Temp, Power, and RoR", color=TRON_WHITE)
    ax1.set_xlabel("Time (seconds)", color=TRON_WHITE)
    ax1.set_ylabel("Temperature (°F)", color=TRON_CYAN)
    ax1.tick_params(axis='y', colors=TRON_CYAN)
    ax1.grid(True, color=TRON_GRID, linestyle=':', alpha=0.5)

    # AX2 (Power Levels)
    ax2.set_ylabel("Power Level (%)", color=TRON_WHITE)
    ax2.set_ylim(0, 100)
    ax2.tick_params(axis='y', colors=TRON_WHITE)
    # Ensure ax2 spine uses TRON_WHITE
    ax2.spines['right'].set_edgecolor(TRON_WHITE) 
    ax2.spines['right'].set_linewidth(1.5)

    # AX3 (RoR)
    # --- DYNAMIC SCALING FIX ---
    max_ror = max(rors) if rors else 0
    # Determine a good auto-limit (e.g., next multiple of 50 or 100)
    if max_ror > 150:
        ror_limit = (int(max_ror / 50) + 1) * 50
    elif max_ror > 100:
        ror_limit = 150
    elif max_ror > 50:
        ror_limit = 100
    else:
        ror_limit = 50
        
    ax3.set_ylabel("RoR (°F/min)", color=TRON_ROR)
    ax3.set_ylim(0, ror_limit) # Set dynamic limit
    ax3.tick_params(axis='y', colors=TRON_ROR)
    # Ensure ax3 spine uses TRON_ROR
    ax3.spines['right'].set_edgecolor(TRON_ROR)
    ax3.spines['right'].set_linewidth(1.5)
    
    # X-Axis and Event Markers
    filtered_events = [event for event in roast_events if event['time'] <= max_data_time]
    for event in filtered_events:
        ax1.axvline(x=event['time'], color='lime', linestyle='-', linewidth=1, alpha=0.7)
        if ax1.get_ylim()[1] > 0:
             ax1.text(event['time'] + 2, ax1.get_ylim()[1]*0.1, event['event'], color='lime', rotation=90, verticalalignment='bottom', fontsize=8)

    # Set the x-axis limit based on data length
    ax1.set_xlim(left=0, right=max_data_time + 5) 

    # Configure X-axis
    ax1.tick_params(axis='x', colors=TRON_WHITE)
    
    # Add combined legend 
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    h3, l3 = ax3.get_legend_handles_labels()
    
    # Create legend with all lines
    leg = ax1.legend(h1+h2+h3, l1+l2+l3, loc='upper left', facecolor=TRON_BLACK, edgecolor=TRON_GRID, fontsize=9)
    
    # Explicitly set the text color of the legend labels to TRON_WHITE
    plt.setp(leg.get_texts(), color=TRON_WHITE) 

    # Set spine colors for AX1
    for spine in ax1.spines.values():
        spine.set_edgecolor(TRON_CYAN)

    canvas.draw()
    
    after_id_update_temp_power_graph = gui.after(1000, update_combined_graph, ax1, ax2, ax3, canvas)

# --- END NEW FUNCTION ---

# NEW HELPER: Calculates DTR for logging
def get_current_dtr_percentage():
    """Calculates and returns the DTR percentage, or None if not started."""
    if first_crack_time > 0:
        current_elapsed_time = timer[0] * 3600 + timer[1] * 60 + timer[2]
        if current_elapsed_time > 0:
            time_since_crack = current_elapsed_time - first_crack_time
            if time_since_crack < 0:
                 return 0.0 # DTR can't be negative
            total_time = current_elapsed_time
            return (time_since_crack / total_time) * 100
    return None

def tempit():
    """
    Reads sensor data twice per second, calculates smoothed bean and inlet temperatures,
    and calculates the Rate of Rise (RoR) once per second.
    """
    global temps, ror_history, smoothed_bt_ror_calc, smoothed_bt_plot, smoothed_ia_plot, timer, air_now, heat_now, roast_start_time, first_crack_time
    ch1 = sensor1.get_currentValue() # Bean Mass Temp - use non-rounded for accuracy
    ch2 = sensor2.get_currentValue() # Inlet Air Temp
    
    # Get current elapsed time from the stopwatch timer
    current_elapsed_time = timer[0] * 3600 + timer[1] * 60 + timer[2]
    
    timetosend = datetime.datetime.now().strftime("%H%M%S")
    
    # Store raw temps, power levels, and timestamp
    # Data stored: [ch1_bt, ch2_inlet_air, air_power, heat_power, timetosend, elapsed_time]
    temps.append([ch1, ch2, air_now, heat_now, timetosend, current_elapsed_time])
    
    # --- Step 1: Apply Rolling Average Filter to Temps ---
    try:
        current_ror_window_seconds = ror_time_window.get()
        if current_ror_window_seconds < 2:
            current_ror_window_seconds = 2 # Need at least 2 data points
    except (ValueError, TclError):
        current_ror_window_seconds = 3 # Default to 3s (FIXED responsiveness)

    # Convert window from seconds to number of samples (at 2 samples/sec)
    num_samples_for_window = current_ror_window_seconds * 2

    # Only proceed if we have enough raw data for the rolling average window
    if len(temps) >= num_samples_for_window:
        
        # Get the last 'n' number of readings for the bean probe (index 0)
        last_n_bt_temps = [temps[i][0] for i in range(-num_samples_for_window, 0)]
        smoothed_bt = sum(last_n_bt_temps) / len(last_n_bt_temps)

        # Get the last 'n' number of readings for the inlet air probe (index 1)
        last_n_ia_temps = [temps[i][1] for i in range(-num_samples_for_window, 0)]
        smoothed_ia = sum(last_n_ia_temps) / len(last_n_ia_temps)
        
        # Store smoothed data for RoR calculation
        smoothed_bt_ror_calc.append(smoothed_bt)
        
        # Store smoothed data for plotting
        smoothed_bt_plot.append(smoothed_bt)
        smoothed_ia_plot.append(smoothed_ia)


    # --- Step 2: Calculate RoR from Smoothed BT (once per second) ---
    # We run this block only on the second sample of each second to update the graph once per second.
    if len(smoothed_bt_ror_calc) % 2 == 0:
        # We need 30 seconds of smoothed data to look back. At 2 samples/sec, this is 60 samples.
        # We need > 60 samples to have a prior point.
        num_samples_for_ror = 60 
        
        if len(smoothed_bt_ror_calc) > num_samples_for_ror:
            # Get the current smoothed temp and the one from 30 seconds ago (60 samples ago)
            current_smoothed_bt = smoothed_bt_ror_calc[-1]
            prior_smoothed_bt = smoothed_bt_ror_calc[-(num_samples_for_ror + 1)]
            
            # Calculate the change over 30 seconds
            temp_change_over_30s = current_smoothed_bt - prior_smoothed_bt
            
            # Extrapolate to a per-minute rate and round to the nearest whole number
            ror = round(temp_change_over_30s * 2) # (since 30 seconds is half a minute)
            
            # RoR history stores the elapsed time directly from the timer (Point 1 fix)
            ror_history.append((current_elapsed_time, ror))

    # --- Step 3: Post-Crack Development Percentage (Runs every 0.5s) ---
    if first_crack_time > 0:
        dtr_percent = get_current_dtr_percentage()
        if dtr_percent is not None:
            # CONSOLE OUTPUT FIX: DTR: X%
            print(f"DTR: {dtr_percent:.2f}%")


def poll_sensors_for_roast_data():
    """If the timer is running, polls sensors to log data and calc RoR."""
    global after_id_poll_sensors
    if state:
        tempit()
    # The after call is required to keep the loop running based on the system clock
    after_id_poll_sensors = gui.after(500, poll_sensors_for_roast_data) 

def poll_sensors_for_display():
    """Continuously polls sensors just to update the GUI display."""
    global after_id_poll_display, last_displayed_bt, last_displayed_ia
    
    # We poll the actual sensor values, regardless of whether the roast is active or logging is running
    current_bt = sensor1.get_currentValue()
    current_ia = sensor2.get_currentValue()
    
    current_bt_round = round(current_bt)
    current_ia_round = round(current_ia)

    # Only update display if temperature has changed by a full degree
    if abs(current_bt_round - last_displayed_bt) >= 1:
        t1disp.set(current_bt_round)
        last_displayed_bt = current_bt_round
    
    if abs(current_ia_round - last_displayed_ia) >= 1:
        t2disp.set(current_ia_round)
        last_displayed_ia = current_ia_round

    # Poll again in 500ms. This loop is now entirely independent of the roast 'state'. (Point 4 fix)
    after_id_poll_display = gui.after(500, poll_sensors_for_display)

def logit(air, heat, time_interval, time_of_log):
    global intervals
    intervals.append([air, heat, time_interval, time_of_log])
    print(f'New Interval {len(intervals)}: Air={air}, Heat={heat}')

def saveit():
    """Saves the intervals, temps, events, and RoR graph to files using the roast_name."""
    global roast_name, fig, intervals, temps, roast_events, first_crack_time
    
    # Check for fig presence to determine which graph to save
    if fig and fig.axes:
        # Since fig now holds the combined graph, we save it as the primary curve
        fig2 = fig # Use fig for saving logic

    if not roast_name or not (temps or intervals or roast_events):
        print("Roast name not set or no data to save.")
        return

    save_dir = "/share/profiles/"
    os.makedirs(save_dir, exist_ok=True)

    today_date = datetime.datetime.now().strftime('%Y-%m-%d')
    base_filename = f"{today_date}_{roast_name}"
    
    # Calculate final DTR percentage for logging (Point 1)
    final_dtr = get_current_dtr_percentage()

    if intervals:
        intervals_path = os.path.join(save_dir, f"{base_filename}-intervals.csv")
        try:
            with open(intervals_path, 'w', newline='') as outfile:
                writer = csv.writer(outfile)
                writer.writerows(intervals)
            print(f"Intervals saved to {intervals_path}")
        except Exception as e:
            print(f"Error saving intervals: {e}")

    if temps:
        temps_path = os.path.join(save_dir, f"{base_filename}-temps.csv")
        try:
            # Add a header row to the CSV for clarity on the new data structure
            # NOTE: Only raw data is saved here, which contains the power levels
            data_to_save = [['Bean_Temp_F', 'Inlet_Temp_F', 'Air_Power_pct', 'Heat_Power_pct', 'Timestamp', 'Elapsed_Time_s']]
            data_to_save.extend(list(temps))
            with open(temps_path, 'w', newline='') as outfile:
                writer = csv.writer(outfile)
                writer.writerows(data_to_save)
            print(f"Temperatures and Power levels saved to {temps_path}")
        except Exception as e:
            print(f"Error saving temps: {e}")
    
    if roast_events:
        events_path = os.path.join(save_dir, f"{base_filename}-events.txt")
        try:
            with open(events_path, 'w') as outfile:
                # Log final DTR at the start of the events file
                if final_dtr is not None and first_crack_time > 0:
                    outfile.write(f"Final Development Time Ratio (DTR): {final_dtr:.2f}%\n")
                    outfile.write(f"First Crack Started at: {time.strftime('%M:%S', time.gmtime(first_crack_time))}\n")
                
                # Log individual events
                for event in roast_events:
                    time_str = time.strftime('%M:%S', time.gmtime(event['time']))
                    outfile.write(f"Event: {event['event']}, Time: {time_str}, Temp: {event['temp']}°F\n")
            print(f"Events saved to {events_path}")
        except Exception as e:
            print(f"Error saving events: {e}")

    # Save the Combined graph
    if fig:
        graph_path = os.path.join(save_dir, f"{base_filename}-combined-curve.jpg")
        try:
            # Set the aspect ratio before saving to prevent the tall image issue
            fig.set_size_inches(9, 7) 
            fig.savefig(graph_path, format='jpg', facecolor=fig.get_facecolor(), bbox_inches='tight')
            print(f"Combined graph saved to {graph_path}")
        except Exception as e:
            print(f"Error saving Combined graph: {e}")

def setpwm(air, heat):
    global start, startint, profile, heat_now, air_now
    
    if air > blower_upper_bound or heat > heat_upper_bound:
        print('Out of bounds for the blower or heater!')
        return

    if not profile:
        if start:
            startint = time.time()
            start = False
            swstart()
        else:
            timetosend = datetime.datetime.now().strftime("%H%M%S")
            log_air = air_now if (air_now != 0 or heat_now != 0) else air
            log_heat = heat_now if (air_now != 0 or heat_now != 0) else heat
            logit(log_air, log_heat, time.time() - startint, timetosend)
        
        startint = time.time()

    blowerpwm.ChangeDutyCycle(air)
    air_now = air
    bpwmdisp.set(air_now)
    jumptoair.delete(0, END)

    heaterpwm.ChangeDutyCycle(heat)
    heat_now = heat
    hpwmdisp.set(heat_now)
    jumptoheat.delete(0, END)

def control(bkill=False, hkill=False):
    """Simplified control logic for setting air and heat safely."""
    target_air = air_now
    if jumptoair.get().isdigit():
        target_air = int(jumptoair.get())

    target_heat = heat_now
    if jumptoheat.get().isdigit():
        target_heat = int(jumptoheat.get())

    if bkill:
        target_air = 0
    if hkill:
        target_heat = 0
    
    # Air always kills heat
    if target_air == 0:
        target_heat = 0

    setpwm(target_air, target_heat)

def update_timeText():
    """ Accurately updates the timer display using elapsed system time. """
    global state, timer, after_id_update_timeText, roast_start_time, last_elapsed_time
    if state:
        # Calculate the delta from the start time
        elapsed = time.time() - roast_start_time
        
        # Convert total seconds to H:M:S format
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)
        
        # Update the timer variable for other functions (like mark_event)
        timer[0] = int(hours)
        timer[1] = int(minutes)
        timer[2] = int(seconds)
        
        timeString = pattern.format(timer[0], timer[1], timer[2])
        timeText.configure(text=timeString)
        
    after_id_update_timeText = gui.after(1000, update_timeText)

def swstart():
    global state, timer, roast_start_time, last_elapsed_time
    
    # If resuming from a pause
    if last_elapsed_time > 0:
          roast_start_time = time.time() - last_elapsed_time
    # If starting fresh
    elif not state:
        roast_start_time = time.time()
        last_elapsed_time = 0
        # REMOVED: No more auto-mark start event
        
    state = True

def swpause():
    global state, last_elapsed_time, roast_start_time
    state = False
    # Record how much time has passed so we can resume accurately
    if roast_start_time > 0:
        last_elapsed_time = time.time() - roast_start_time

def swreset():
    global timer, temps, ror_history, roast_events, smoothed_bt_ror_calc, smoothed_bt_plot, smoothed_ia_plot, after_id_auto_mark_start, roast_start_time, last_elapsed_time, first_crack_time
    global last_displayed_bt, last_displayed_ia
    swpause()
    # Cancel the pending auto-mark event if the roast is reset
    if after_id_auto_mark_start:
        gui.after_cancel(after_id_auto_mark_start)
        after_id_auto_mark_start = None

    # Reset timekeeping variables
    roast_start_time = 0
    last_elapsed_time = 0
    first_crack_time = 0 # Reset first crack tracker
    timer = [0, 0, 0]
    timeText.configure(text='00:00:00')
    
    # Reset display temp trackers
    last_displayed_bt = 0
    last_displayed_ia = 0
    
    # Clear data logs
    temps.clear()
    ror_history.clear()
    smoothed_bt_ror_calc.clear()
    smoothed_bt_plot.clear()
    smoothed_ia_plot.clear()
    roast_events.clear()

def loadit():
    """Loads a profile from a CSV file. Returns True on success, False on failure/cancel."""
    global intervals, roast_name
    try:
        filepath = filedialog.askopenfilename(initialdir="/share/profiles/")
        if filepath:
            with open(filepath, 'r') as infile:
                reader = csv.reader(infile)
                rawimport = list(reader)
                intervals.clear()
                for row in rawimport:
                    # Expecting rows with at least 3 values: air, heat, duration
                    if len(row) >= 3:
                        intervals.append([float(val) for val in row[:3]])
                
                profile_name_with_ext = os.path.basename(filepath)
                profiledisplayname.set(profile_name_with_ext)

                # Set the main roast_name from the loaded file for saving purposes
                base_name = profile_name_with_ext.replace("-intervals.csv", "")
                # Strip date if it exists
                try:
                    datetime.datetime.strptime(base_name[:10], '%Y-%m-%d')
                    roast_name = base_name[11:]
                except ValueError:
                    roast_name = base_name

                print(f'FILENAME: {profile_name_with_ext}, intervals loaded.')
                print(f"Roast name for saving set to: {roast_name}")
                return True # Indicate success
    except Exception as e:
        print(f"Failed to load profile: {e}")
    return False # Indicate failure or cancel

def runit():
    global profile, profile_running
    if not intervals:
        print("No profile loaded to run.")
        return

    profile = True
    profile_running = True
    swstart()
    try:
        for air, heat, duration in intervals:
            if not profile_running:
                print("Profile run stopped by user.")
                break
            print(f'Running interval: Air={air}, Heat={heat}, Duration={duration}s')
            setpwm(int(round(air)), int(round(heat)))
            
            # Sleep in 1-second increments to allow for interruption
            for _ in range(int(duration)):
                if not profile_running:
                    break
                time.sleep(1)
            
            # Check again in case the stop was requested during the sleep loop
            if not profile_running:
                print("Profile run stopped by user during interval.")
                break

    except KeyboardInterrupt:
        print("Profile run interrupted.")
    finally:
        profile = False
        profile_running = False
        swpause()
        setpwm(0, 0)
        print('Profile run finished or stopped.')
        jumptoair.focus_set()

def looprunner():
    Thread(target=runit, daemon=True).start()

def reset():
    global intervals, start, profile
    intervals = []
    start = True
    profile = False
    swreset()
    print('Intervals and roast data reset.')
    profiledisplayname.set('none')

def start_new_roast():
    """Resets all data and prompts for a new roast name."""
    global roast_name
    reset()
    new_name = simpledialog.askstring("New Roast", "Please enter a name for the new roast:")
    if new_name:
        roast_name = new_name
        profiledisplayname.set(roast_name)
    else:
        roast_name = f"untitled-roast-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        profiledisplayname.set(roast_name)

    
    gui.wm_title(f'KALDI - {roast_name}')
    print(f"Started new roast: {roast_name}")

def mark_event(event_name):
    """Marks a roast event at the current time."""
    global roast_events, timer, first_crack_time
    if not state:
        # Allow marking 'End' even if timer is stopped, for shutdown sequence
        if event_name != "End":
            print("Cannot mark event: stopwatch is not running.")
            return

    current_time_seconds = timer[0] * 3600 + timer[1] * 60 + timer[2]
    
    # Store First Crack time
    if event_name == "First Crack":
        if first_crack_time == 0:
            first_crack_time = current_time_seconds
            print(f"--- FIRST CRACK STARTED at {time.strftime('%M:%S', time.gmtime(first_crack_time))} ---")
        else:
            print("First Crack time already logged.")

    # Use the current smoothed bean temp for the event log
    current_temp = round(smoothed_bt_plot[-1]) if smoothed_bt_plot else round(sensor1.get_currentValue())
    roast_events.append({'time': current_time_seconds, 'event': event_name, 'temp': current_temp})
    time_str = pattern.format(timer[0], timer[1], timer[2])
    print(f"EVENT MARKED: {event_name} at {time_str} ({current_temp}°F)")

def close_window(event=None):
    global after_id_update_graph, after_id_update_temp_power_graph, after_id_update_timeText, after_id_poll_sensors, after_id_poll_display, air_now, heat_now, after_id_auto_mark_start
    
    if state: # Only mark end if a roast was active
        mark_event("End")
    
    # Cancel all graph/timer loops
    if after_id_update_temp_power_graph:
        gui.after_cancel(after_id_update_temp_power_graph)
    if after_id_update_timeText:
        gui.after_cancel(after_id_update_timeText)
    if after_id_poll_sensors:
        gui.after_cancel(after_id_poll_sensors)
    # NOTE: poll_sensors_for_display is left running if the app is not destroyed
    if after_id_poll_display:
        gui.after_cancel(after_id_poll_display) # Cancel display poll before destroying GUI

    if after_id_auto_mark_start:
        gui.after_cancel(after_id_auto_mark_start)
    
    saveit()

    # Direct hardware shutdown
    blowerpwm.ChangeDutyCycle(0)
    heaterpwm.ChangeDutyCycle(0)
    air_now = 0
    heat_now = 0

    GPIO.cleanup()
    gui.destroy()

def killall(event=None):
    global profile_running, air_now, heat_now, after_id_auto_mark_start
    mark_event("End") # Mark the end of the roast
    profile_running = False
    swpause()

    if after_id_auto_mark_start:
        gui.after_cancel(after_id_auto_mark_start)
        after_id_auto_mark_start = None

    saveit()
    
    # Direct hardware shutdown and state update
    blowerpwm.ChangeDutyCycle(0)
    heaterpwm.ChangeDutyCycle(0)
    air_now = 0
    heat_now = 0
    bpwmdisp.set(0)
    hpwmdisp.set(0)
    
    # NOTE: poll_sensors_for_display continues to run (Point 4 fix)


def go(event=None):
    control()

def adjust_value(element, change):
    if element == 'air':
        current_value = air_now
        entry_widget = jumptoair
    else:  
        current_value = heat_now
        entry_widget = jumptoheat

    if current_value > 0:
        new_value = max(0, current_value + change)
        entry_widget.delete(0, END)
        entry_widget.insert(0, str(new_value))
        control()
    else:
        print(f'{element.capitalize()} is off. Use the SET field to start.')
        entry_widget.delete(0, END)

GPIO.setmode(GPIO.BOARD)

# assigning pin 10 - HEATER
GPIO.setup(10, GPIO.OUT)
GPIO.output(10, 0)

# assigning pin 8 - BLOWER
GPIO.setup(8, GPIO.OUT)
GPIO.output(8, 0)

# starting PWM for heater
heaterpwm = GPIO.PWM(10, 60)
heaterpwm.start(0)

# starting PWM for the blower
blowerpwm = GPIO.PWM(8, 59)
blowerpwm.start(0)

# --- Define functions for transitioning UI ---

def transition_to_main_app():
    """Hides startup frame, shows main frame, and starts processes."""
    global ax1, ax2, ax3, canvas
    startup_frame.pack_forget()
    main_frame.pack(fill="both", expand=True)
    gui.wm_title(f'KALDI - {roast_name}')
    
    # Key Bindings are now set only when the main app is active
    gui.bind('<Up>', lambda e: adjust_value('heat', 1))
    gui.bind('<Down>', lambda e: adjust_value('heat', -1))
    gui.bind('<w>', lambda e: adjust_value('air', 1))
    gui.bind('<s>', lambda e: adjust_value('air', -1))
    gui.bind('<Control-Return>', go)
    gui.bind('<Control-x>', close_window)
    gui.bind('<Control-k>', killall)
    gui.protocol("WM_DELETE_WINDOW", close_window)
    
    # Start recurring tasks and create the graph window
    # NEW: Triple-Axis Combined Graph
    ax1, ax2, ax3, canvas = create_triple_axis_graph_window()
    update_combined_graph(ax1, ax2, ax3, canvas)
    
    update_timeText()
    poll_sensors_for_roast_data()
    # poll_sensors_for_display() # REMOVED: Now started in __main__
    
# --- Build the Startup UI ---

def setup_startup_frame():
    startup_frame.pack(pady=200) # Increased vertical padding
    Label(startup_frame, text="Start a new roast or load an existing profile.", font=("Helvetica", 18), bg=TRON_BLACK, fg=TRON_WHITE).pack(pady=40)
    
    name_frame = Frame(startup_frame, bg=TRON_BLACK)
    Label(name_frame, text="New Roast Name:", bg=TRON_BLACK, fg=TRON_CYAN, font=('Helvetica', 14)).pack(side=LEFT, padx=10)
    
    # Revert to standard Entry field style for the startup screen
    name_entry = Entry(name_frame, width=25, bg=TRON_GRID, fg=TRON_WHITE, insertbackground=TRON_CYAN, bd=2, relief=FLAT, font=('Helvetica', 14))
    name_entry.pack(side=LEFT)
    
    name_frame.pack(pady=30)
    name_entry.focus_set()

    def on_start(event=None):
        global roast_name
        roast_name = name_entry.get()
        if not roast_name:
            roast_name = f"untitled-roast-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        profiledisplayname.set(roast_name)
        transition_to_main_app()

    def on_load():
        if loadit():
            transition_to_main_app()

    name_entry.bind('<Return>', on_start)

    button_frame = Frame(startup_frame, bg=TRON_BLACK)
    button_frame.pack(pady=40)
    
    # STARTUP BUTTON STYLING (Same as main for consistency, increased size)
    Button(button_frame, text="Load Profile", command=on_load, bg=TRON_BLACK, fg=TRON_CYAN, activebackground=TRON_CYAN, activeforeground=TRON_BLACK, relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=2, padx=15, font=('Helvetica', 12, 'bold')).pack(side=LEFT, padx=20)
    Button(button_frame, text="Start New Roast", command=on_start, bg=TRON_BLACK, fg=TRON_CYAN, activebackground=TRON_CYAN, activeforeground=TRON_BLACK, relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=2, padx=15, font=('Helvetica', 12, 'bold')).pack(side=LEFT, padx=20)

# --- Build the Main Roasting UI ---

def setup_main_frame():
    # Helper for TRON button styling
    def create_tron_button(parent, text, command, color=TRON_CYAN, hthickness=2, font_size=12, width_char=None):
        return Button(parent, text=text, command=command, 
                      bg=TRON_BLACK, fg=color, 
                      activebackground=color, activeforeground=TRON_BLACK, 
                      relief=FLAT, highlightbackground=color, highlightthickness=hthickness,
                      font=('Helvetica', font_size, 'bold'), width=width_char)

    # --- GUI LAYOUT ---
    
    # Window Width (700)
    WINDOW_W = 700
    
    # --- CALCULATIONS FOR CENTERING ---
    # Width of the content block (approximately the Power displays width)
    # Air Power (250) + Gap (~50) + Heat Power (250) = 550
    # Width of the widest element (Console/Button Row) is 650
    
    CONSOLE_W = 650
    CENTER_OFFSET = (WINDOW_W - CONSOLE_W) // 2 # 700 - 650 = 50. 50 // 2 = 25
    
    # Base padding/dimensions
    PAD_X = CENTER_OFFSET # Start everything at X=25
    BASE_Y = 20
    
    # --- ROW 1: Roast Name | Timer | RoR Window ---
    
    # Roast Name (X=25)
    Label(main_frame, text='Roast Name', anchor='w', font=('Helvetica', 10, 'bold'), bg=TRON_BLACK, fg=TRON_WHITE).place(x=PAD_X, y=BASE_Y, height=20, width=150)
    name_display_frame = Frame(main_frame, bg=TRON_CYAN, highlightbackground=TRON_CYAN, highlightthickness=1)
    name_display_frame.place(x=PAD_X, y=BASE_Y + 20, height=30, width=202) 
    Label(name_display_frame, textvariable=profiledisplayname, bg=TRON_GRID, fg=TRON_CYAN, anchor='w', font=('Helvetica', 14, 'italic'), padx=4).place(x=1, y=1, height=28, width=200)

    # Timer (Centered Position Calculation: X = (WINDOW_W / 2) - (Timer Width / 2) = 350 - 102 = 248)
    TIMER_W = 200
    TIMER_X = (WINDOW_W - TIMER_W) // 2
    
    Label(main_frame, text="TIME", justify=CENTER, font=('Helvetica', 10, 'bold'), bg=TRON_BLACK, fg=TRON_WHITE).place(x=TIMER_X, y=BASE_Y, width=TIMER_W, height=20)
    global timeText, timer, pattern
    time_display_frame = Frame(main_frame, bg=TRON_CYAN, highlightbackground=TRON_CYAN, highlightthickness=2)
    time_display_frame.place(x=TIMER_X - 2, y=BASE_Y + 20, width=TIMER_W + 4, height=54) # Taller & Wider
    timeText = Label(time_display_frame, text="00:00:00", font=("Helvetica", 35, 'bold'), bg=TRON_BLACK, fg=TRON_WHITE)
    timeText.place(x=2, y=2, width=TIMER_W, height=50)
    timer = [0,0,0]
    pattern = '{0:02d}:{1:02d}:{2:02d}'

    # RoR Window (Aligned to the Right: X = WINDOW_W - PAD_X - 150)
    ROR_W = 150
    ROR_X = WINDOW_W - PAD_X - ROR_W
    
    Label(main_frame, text="RoR Window (s):", anchor='e', font=('Helvetica', 10, 'bold'), bg=TRON_BLACK, fg=TRON_WHITE).place(x=ROR_X, y=BASE_Y, height=20, width=ROR_W)
    ror_entry = Entry(main_frame, textvariable=ror_time_window, width=5, bg=TRON_GRID, fg=TRON_CYAN, insertbackground=TRON_CYAN, bd=0, relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=1, justify='center', font=('Helvetica', 14))
    ror_entry.place(x=WINDOW_W - PAD_X - 100, y=BASE_Y + 20, width=100, height=30)
    
    # Start/Stop/Reset Buttons (Centered horizontally)
    BTN_Y1 = BASE_Y + 80
    
    BTN_START_X = TIMER_X - 2 # Align start button with timer display start
    create_tron_button(main_frame, 'Start', swstart, font_size=11).place(x=BTN_START_X, y=BTN_Y1, height=30, width=65)
    create_tron_button(main_frame, 'Reset', swreset, font_size=11).place(x=BTN_START_X + 65, y=BTN_Y1, height=30, width=65)
    create_tron_button(main_frame, 'Stop', swpause, font_size=11).place(x=BTN_START_X + 130, y=BTN_Y1, height=30, width=70)


    # --- ROW 2: Power Displays (Centered Group) ---
    POWER_Y = BTN_Y1 + 60
    POWER_W = 250
    POWER_H = 100
    GROUP_W = POWER_W * 2 + 50 # 550 (250 Air + 50 Gap + 250 Heat)
    GROUP_X = (WINDOW_W - GROUP_W) // 2
    
    # AIR POWER
    AIR_X = GROUP_X
    Label(main_frame, text='AIR % POWER', anchor='center', bg=TRON_BLACK, fg=TRON_WHITE, font=('Helvetica', 12, 'bold')).place(x=AIR_X, y=POWER_Y, height=25, width=POWER_W)
    air_power_frame = Frame(main_frame, bg=TRON_AIR_POWER, highlightbackground=TRON_AIR_POWER, highlightthickness=3) # Thicker Border
    air_power_frame.place(x=AIR_X, y=POWER_Y + 25, height=POWER_H + 4, width=POWER_W + 4)
    Label(air_power_frame, textvariable=bpwmdisp, bg=TRON_BLACK, fg=TRON_AIR_POWER, font=('Helvetica', 80, 'bold')).place(x=2, y=2, height=POWER_H, width=POWER_W)
    
    # HEAT POWER
    HEAT_X = AIR_X + POWER_W + 50
    Label(main_frame, text='HEAT % POWER', anchor='center', bg=TRON_BLACK, fg=TRON_WHITE, font=('Helvetica', 12, 'bold')).place(x=HEAT_X, y=POWER_Y, height=25, width=POWER_W)
    heat_power_frame = Frame(main_frame, bg=TRON_HEAT_POWER, highlightbackground=TRON_HEAT_POWER, highlightthickness=3) # Thicker Border
    heat_power_frame.place(x=HEAT_X, y=POWER_Y + 25, height=POWER_H + 4, width=POWER_W + 4)
    Label(heat_power_frame, textvariable=hpwmdisp, bg=TRON_BLACK, fg=TRON_HEAT_POWER, font=('Helvetica', 80, 'bold')).place(x=2, y=2, height=POWER_H, width=POWER_W)


    # --- ROW 3: Set Controls (Centered Group) ---
    SET_Y = POWER_Y + POWER_H + 60
    LABEL_W = 150
    ENTRY_W = 100
    UPDATE_W = 100
    
    SET_GROUP_W = LABEL_W + 10 + ENTRY_W + 30 + UPDATE_W # ~390
    SET_GROUP_X = (WINDOW_W - SET_GROUP_W) // 2
    
    
    # SET AIR
    Label(main_frame, text='SET AIR:', anchor='e', bg=TRON_BLACK, fg=TRON_WHITE, font=('Helvetica', 12)).place(x=SET_GROUP_X, y=SET_Y, width=LABEL_W, height=30)
    global jumptoair, jumptoheat
    jumptoair = Entry(main_frame, bg=TRON_GRID, fg=TRON_AIR_POWER, insertbackground=TRON_AIR_POWER, bd=0, relief=FLAT, highlightbackground=TRON_AIR_POWER, highlightthickness=1, font=('Helvetica', 14))
    jumptoair.place(x=SET_GROUP_X + LABEL_W + 10, y=SET_Y, width=ENTRY_W, height=30)
    
    # SET HEAT
    Label(main_frame, text='SET HEAT:', anchor='e', bg=TRON_BLACK, fg=TRON_WHITE, font=('Helvetica', 12)).place(x=SET_GROUP_X, y=SET_Y + 40, width=LABEL_W, height=30)
    jumptoheat = Entry(main_frame, bg=TRON_GRID, fg=TRON_HEAT_POWER, insertbackground=TRON_HEAT_POWER, bd=0, relief=FLAT, highlightbackground=TRON_HEAT_POWER, highlightthickness=1, font=('Helvetica', 14))
    jumptoheat.place(x=SET_GROUP_X + LABEL_W + 10, y=SET_Y + 40, width=ENTRY_W, height=30)

    # Update Levels Button (Adjusted position)
    create_tron_button(main_frame, 'Update\nLevels', go, font_size=12).place(x=SET_GROUP_X + LABEL_W + ENTRY_W + 30, y=SET_Y, height=70, width=UPDATE_W)
    

    # --- ROW 4: Temperature Display (Centered Group) ---
    TEMP_Y = SET_Y + 120
    TEMP_LABEL_W = 180
    TEMP_VALUE_W = 100
    
    TEMP_GROUP_W = TEMP_LABEL_W + 10 + TEMP_VALUE_W + 20 + 40 # ~350
    TEMP_GROUP_X = (WINDOW_W - TEMP_GROUP_W) // 2
    
    # BEAN MASS (TRON_CYAN)
    Label(main_frame, text="Bean Mass:", anchor='e', font=('Helvetica', 18), bg=TRON_BLACK, fg=TRON_CYAN).place(x=TEMP_GROUP_X, y=TEMP_Y, height=60, width=TEMP_LABEL_W)
    Label(main_frame, textvariable=t1disp, bg=TRON_BLACK, fg=TRON_CYAN, font=('Helvetica', 45, 'bold')).place(x=TEMP_GROUP_X + TEMP_LABEL_W + 10, y=TEMP_Y, height=60, width=TEMP_VALUE_W)
    Label(main_frame, text="°F", anchor='w', font=('Helvetica', 18), bg=TRON_BLACK, fg=TRON_CYAN).place(x=TEMP_GROUP_X + TEMP_LABEL_W + TEMP_VALUE_W + 20, y=TEMP_Y, height=60, width=40)
    
    # INLET AIR (TRON_MAGENTA)
    Label(main_frame, text="Inlet Air:", anchor='e', font=('Helvetica', 18), bg=TRON_BLACK, fg=TRON_MAGENTA).place(x=TEMP_GROUP_X, y=TEMP_Y + 70, height=60, width=TEMP_LABEL_W)
    Label(main_frame, textvariable=t2disp, bg=TRON_BLACK, fg=TRON_MAGENTA, font=('Helvetica', 45, 'bold')).place(x=TEMP_GROUP_X + TEMP_LABEL_W + 10, y=TEMP_Y + 70, height=60, width=TEMP_VALUE_W)
    Label(main_frame, text="°F", anchor='w', font=('Helvetica', 18), bg=TRON_BLACK, fg=TRON_MAGENTA).place(x=TEMP_GROUP_X + TEMP_LABEL_W + TEMP_VALUE_W + 20, y=TEMP_Y + 70, height=60, width=40)

    # --- ROW 5: Event Marking (Centered Group) ---
    EVENT_Y = TEMP_Y + 140
    
    # Calculate total width of the button group for centering (4 * 120px est button width + 5*10px padding)
    BTN_SPACE_W = (120 * 4) + (5 * 10) # ~530px
    EVENT_FRAME_W = BTN_SPACE_W 
    EVENT_FRAME_X = (WINDOW_W - EVENT_FRAME_W) // 2 # Center the frame itself
    
    event_frame = Frame(main_frame, bg=TRON_BLACK)
    event_frame.place(x=EVENT_FRAME_X, y=EVENT_Y, width=EVENT_FRAME_W, height=40)
    
    # Removed "Mark Event:" Label.
    # We use pack with expand=True inside the frame to center the remaining buttons.
    create_tron_button(event_frame, "Start", lambda: mark_event("Start"), font_size=11).pack(side=LEFT, padx=10, fill=X, expand=True)
    create_tron_button(event_frame, "Yellowing", lambda: mark_event("Yellowing"), font_size=11).pack(side=LEFT, padx=10, fill=X, expand=True)
    create_tron_button(event_frame, "First Crack", lambda: mark_event("First Crack"), font_size=11).pack(side=LEFT, padx=10, fill=X, expand=True)
    create_tron_button(event_frame, "End", lambda: mark_event("End"), font_size=11).pack(side=LEFT, padx=10, fill=X, expand=True)


    # --- ROW 6: Main Controls and Kill Switches (Centered Group) ---
    BTN_Y2 = EVENT_Y + 60
    BTN_W = 150
    GROUP_4_BUTTONS_W = BTN_W * 4 + 45 # 645 (4*150 + 3*15)
    GROUP_4_BUTTONS_X = (WINDOW_W - GROUP_4_BUTTONS_W) // 2
    
    # Main Controls
    X1 = GROUP_4_BUTTONS_X
    X2 = X1 + BTN_W + 15
    X3 = X2 + BTN_W + 15
    X4 = X3 + BTN_W + 15
    
    create_tron_button(main_frame, 'New Roast', start_new_roast, hthickness=2).place(x=X1, y=BTN_Y2, width=BTN_W, height=40)
    create_tron_button(main_frame, 'Run Profile', looprunner, hthickness=2).place(x=X2, y=BTN_Y2, width=BTN_W, height=40)
    create_tron_button(main_frame, "Load Profile...", loadit, hthickness=2).place(x=X3, y=BTN_Y2, width=BTN_W, height=40)
    create_tron_button(main_frame, "EXIT", close_window, hthickness=2).place(x=X4, y=BTN_Y2, width=BTN_W, height=40)

    # Kill Switches (Centered below the Run Profile/Load Profile area)
    KILL_Y = BTN_Y2 + 50
    KILL_W = 70
    
    # Kill Group Calculation: Total Width = BTN_W + 15 + KILL_W + 10 + KILL_W = 245
    KILL_GROUP_W = BTN_W + 15 + KILL_W + 10 + KILL_W
    KILL_GROUP_X = (WINDOW_W - KILL_GROUP_W) // 2
    
    # Kill All
    KILL_ALL_X = KILL_GROUP_X
    create_tron_button(main_frame, 'Kill All', killall, color=TRON_HEAT_POWER, hthickness=3).place(x=KILL_ALL_X, y=KILL_Y, width=BTN_W, height=35)
    
    # Kill Air/Heat
    KILL_AIR_X = KILL_ALL_X + BTN_W + 15
    create_tron_button(main_frame, 'Kill Air', lambda: control(bkill=True), color=TRON_AIR_POWER, hthickness=2, font_size=11).place(x=KILL_AIR_X, y=KILL_Y, width=KILL_W, height=35)
    create_tron_button(main_frame, 'Kill Heat', lambda: control(hkill=True), color=TRON_HEAT_POWER, hthickness=2, font_size=11).place(x=KILL_AIR_X + KILL_W + 10, y=KILL_Y, width=KILL_W, height=35)
    
    
    # --- ROW 7: CONSOLE OUTPUT ---
    CONSOLE_Y = KILL_Y + 50
    CONSOLE_W = 650
    CONSOLE_X = (WINDOW_W - CONSOLE_W) // 2
    
    console_frame = Frame(main_frame, bg=TRON_CYAN, highlightbackground=TRON_CYAN, highlightthickness=1)
    console_frame.place(x=CONSOLE_X, y=CONSOLE_Y, height=150, width=CONSOLE_W + 2) # Taller Console
    console_output = Text(console_frame, bg=TRON_BLACK, fg=TRON_CYAN, state='disabled', relief=FLAT)
    console_output.place(x=1, y=1, height=148, width=CONSOLE_W)
    sys.stdout = TextRedirector(console_output)


# --- MAIN APP START ---
if __name__ == "__main__":
    setup_main_frame()
    setup_startup_frame()
    # Point 4 Fix: Start the non-logging display poll immediately and independently.
    poll_sensors_for_display() 
    gui.mainloop()