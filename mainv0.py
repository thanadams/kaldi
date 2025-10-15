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
after_id_update_graph = None
after_id_update_timeText = None
after_id_poll_sensors = None
after_id_poll_display = None

# Using deque for memory efficiency, stores the last 10 minutes of data (600 seconds)
temps = collections.deque(maxlen=600)
ror_history = collections.deque(maxlen=600)
intervals = []
roast_events = []
start = True
profile = False

heat_upper_bound = 100
blower_upper_bound = 100

air_now = 0
heat_now = 0

roast_name = ""
fig = None 
profile_running = False

# --- GUI SETUP ---
gui = Tk()
gui.title("KALDI Roaster Control")
gui.geometry("500x700+30+30") 
gui.configure(bg=TRON_BLACK)

# Create frames for swapping between startup and main UI
startup_frame = Frame(gui, bg=TRON_BLACK)
main_frame = Frame(gui, bg=TRON_BLACK)

# --- Tkinter Variables ---
bpwmdisp = StringVar()
bpwmdisp.set(air_now)
hpwmdisp = StringVar()
hpwmdisp.set(heat_now)

ch1_val = round(sensor1.get_currentValue())
ch2_val = round(sensor2.get_currentValue())

t1disp = StringVar()
t1disp.set(ch1_val)
t2disp = StringVar()
t2disp.set(ch2_val)

profiledisplayname = StringVar()
profiledisplayname.set('none')

# Variable for the configurable RoR time window
ror_time_window = IntVar()
ror_time_window.set(15) # Default to 15 seconds

def create_graph_window():
    """Creates a new window for the live RoR graph with TRON styling."""
    global fig
    graph_window = Toplevel(gui)
    graph_window.wm_title("Rate of Rise (RoR)")
    graph_window.geometry("800x600+550+30")
    graph_window.configure(bg=TRON_BLACK)

    fig = plt.Figure(figsize=(7, 5), dpi=100)
    fig.patch.set_facecolor(TRON_BLACK)
    ax = fig.add_subplot(111)
    ax.set_facecolor(TRON_BLACK)
    
    canvas = FigureCanvasTkAgg(fig, master=graph_window)
    canvas.get_tk_widget().pack(side=TOP, fill=BOTH, expand=1)
    canvas._tkcanvas.pack(side=TOP, fill=BOTH, expand=1)

    return ax, canvas

def update_graph(ax, canvas):
    """Clears and redraws the RoR graph with the latest data and TRON styling."""
    global after_id_update_graph
    ax.clear()

    if len(ror_history) > 1:
        times, rors = zip(*ror_history)
        ax.plot(times, rors, color=TRON_CYAN, marker='o', linestyle='-', markersize=2)
    
    # Draw event markers
    for event in roast_events:
        ax.axvline(x=event['time'], color=TRON_MAGENTA, linestyle='--', linewidth=1)
        ax.text(event['time'] + 2, ax.get_ylim()[1]*0.9, event['event'], color=TRON_MAGENTA, rotation=90, verticalalignment='top')

    ax.set_title("Rate of Rise", color=TRON_WHITE)
    ax.set_xlabel("Time (seconds)", color=TRON_WHITE)
    ax.set_ylabel("RoR (°F / min)", color=TRON_WHITE)
    
    ax.grid(True, color=TRON_GRID)
    ax.tick_params(axis='x', colors=TRON_WHITE)
    ax.tick_params(axis='y', colors=TRON_WHITE)
    
    for spine in ax.spines.values():
        spine.set_edgecolor(TRON_CYAN)

    canvas.draw()
    
    after_id_update_graph = gui.after(1000, update_graph, ax, canvas)

def tempit():
    """Reads sensor data ONLY for logging and RoR calculation during a roast."""
    global temps, ror_history, timer
    ch1 = round(sensor1.get_currentValue()) # Bean Mass Temp
    ch2 = round(sensor2.get_currentValue()) # Inlet Air Temp
    
    timetosend = datetime.datetime.now().strftime("%H%M%S")
    
    # Store temps with Bean Mass (ch1) first for RoR calculation
    temps.append([ch1, ch2, timetosend])
    
    try:
        current_ror_window = ror_time_window.get()
        if current_ror_window < 2:
            current_ror_window = 2 # Need at least 2 data points for a calculation
    except (ValueError, TclError):
        current_ror_window = 15 # Default to a safe value on error

    if len(temps) >= current_ror_window:
        # Calculate the temperature change over the defined window
        temp_change = temps[-1][0] - temps[-current_ror_window][0]
        # Extrapolate this change to a per-minute rate for standard display
        ror = (temp_change / current_ror_window) * 60
        
        current_time_seconds = timer[0] * 3600 + timer[1] * 60 + timer[2]
        ror_history.append((current_time_seconds, ror))

def poll_sensors_for_roast_data():
    """If the timer is running, polls sensors to log data and calc RoR."""
    global after_id_poll_sensors
    if state:
        tempit()
    after_id_poll_sensors = gui.after(1000, poll_sensors_for_roast_data)

def poll_sensors_for_display():
    """Continuously polls sensors just to update the GUI display."""
    global after_id_poll_display
    ch1 = round(sensor1.get_currentValue()) # Bean Mass Temp
    ch2 = round(sensor2.get_currentValue()) # Inlet Air Temp
    t1disp.set(ch1)
    t2disp.set(ch2)
    after_id_poll_display = gui.after(1000, poll_sensors_for_display)

def logit(air, heat, time_interval, time_of_log):
    global intervals
    intervals.append([air, heat, time_interval, time_of_log])
    print(f'New Interval {len(intervals)}: Air={air}, Heat={heat}')

def saveit():
    """Saves the intervals, temps, events, and RoR graph to files using the roast_name."""
    global roast_name, fig, intervals, temps, roast_events

    if not roast_name or not (temps or intervals or roast_events):
        print("Roast name not set or no data to save.")
        return

    save_dir = "/share/profiles/"
    os.makedirs(save_dir, exist_ok=True)

    today_date = datetime.datetime.now().strftime('%Y-%m-%d')
    base_filename = f"{today_date}_{roast_name}"

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
            with open(temps_path, 'w', newline='') as outfile:
                writer = csv.writer(outfile)
                writer.writerows(list(temps))
            print(f"Temperatures saved to {temps_path}")
        except Exception as e:
            print(f"Error saving temps: {e}")
    
    if roast_events:
        events_path = os.path.join(save_dir, f"{base_filename}-events.txt")
        try:
            with open(events_path, 'w') as outfile:
                for event in roast_events:
                    time_str = time.strftime('%M:%S', time.gmtime(event['time']))
                    outfile.write(f"Event: {event['event']}, Time: {time_str}, Temp: {event['temp']}°F\n")
            print(f"Events saved to {events_path}")
        except Exception as e:
            print(f"Error saving events: {e}")

    if fig:
        graph_path = os.path.join(save_dir, f"{base_filename}-ror-curve.jpg")
        try:
            fig.savefig(graph_path, format='jpg', facecolor=fig.get_facecolor(), bbox_inches='tight')
            print(f"RoR graph saved to {graph_path}")
        except Exception as e:
            print(f"Error saving graph: {e}")

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
    
    if target_air == 0:
        target_heat = 0

    setpwm(target_air, target_heat)

def update_timeText():
    global state, timer, after_id_update_timeText
    if state:
        timer[2] += 1       
        if timer[2] >= 60:
            timer[2] = 0
            timer[1] += 1
        if timer[1] >= 60:
            timer[0] += 1
            timer[1] = 0
        timeString = pattern.format(timer[0], timer[1], timer[2])
        timeText.configure(text=timeString)
    after_id_update_timeText = gui.after(1000, update_timeText)

def swstart():
    global state, timer
    # Automatically mark the 'Start' event only if the timer is at 00:00:00
    if timer == [0, 0, 0] and not state:
        state = True
        mark_event("Start")
    else:
        state = True

def swpause():
    global state
    state = False

def swreset():
    global timer, temps, ror_history, roast_events
    swpause()
    timer = [0, 0, 0]
    timeText.configure(text='00:00:00')
    temps.clear()
    ror_history.clear()
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
    global roast_events, timer
    if not state:
        # Allow marking 'End' even if timer is stopped, for shutdown sequence
        if event_name != "End":
            print("Cannot mark event: stopwatch is not running.")
            return

    current_time_seconds = timer[0] * 3600 + timer[1] * 60 + timer[2]
    current_temp = t1disp.get()
    roast_events.append({'time': current_time_seconds, 'event': event_name, 'temp': current_temp})
    time_str = pattern.format(timer[0], timer[1], timer[2])
    print(f"EVENT MARKED: {event_name} at {time_str} ({current_temp}°F)")

def close_window(event=None):
    global after_id_update_graph, after_id_update_timeText, after_id_poll_sensors, after_id_poll_display, air_now, heat_now
    
    if state: # Only mark end if a roast was active
        mark_event("End")
    
    if after_id_update_graph:
        gui.after_cancel(after_id_update_graph)
    if after_id_update_timeText:
        gui.after_cancel(after_id_update_timeText)
    if after_id_poll_sensors:
        gui.after_cancel(after_id_poll_sensors)
    if after_id_poll_display:
        gui.after_cancel(after_id_poll_display)
    
    saveit()

    # Direct hardware shutdown
    blowerpwm.ChangeDutyCycle(0)
    heaterpwm.ChangeDutyCycle(0)
    air_now = 0
    heat_now = 0

    GPIO.cleanup()
    gui.destroy()

def killall(event=None):
    global profile_running, air_now, heat_now
    mark_event("End") # Mark the end of the roast
    profile_running = False
    swpause()
    saveit()
    
    # Direct hardware shutdown and state update
    blowerpwm.ChangeDutyCycle(0)
    heaterpwm.ChangeDutyCycle(0)
    air_now = 0
    heat_now = 0
    bpwmdisp.set(0)
    hpwmdisp.set(0)


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
    ax, canvas = create_graph_window()
    update_graph(ax, canvas)
    update_timeText()
    poll_sensors_for_roast_data()
    poll_sensors_for_display()

# --- Build the Startup UI ---

def setup_startup_frame():
    startup_frame.pack(pady=150)
    Label(startup_frame, text="Start a new roast or load an existing profile.", font=("Helvetica", 14), bg=TRON_BLACK, fg=TRON_WHITE).pack(pady=30)
    
    name_frame = Frame(startup_frame, bg=TRON_BLACK)
    Label(name_frame, text="New Roast Name:", bg=TRON_BLACK, fg=TRON_CYAN).pack(side=LEFT, padx=5)
    name_entry = Entry(name_frame, width=20, bg=TRON_GRID, fg=TRON_WHITE, insertbackground=TRON_CYAN, bd=2, relief=FLAT)
    name_entry.pack(side=LEFT)
    name_frame.pack(pady=20)
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
    button_frame.pack(pady=30)
    
    Button(button_frame, text="Load Profile", command=on_load, bg=TRON_BLACK, fg=TRON_CYAN, activebackground=TRON_CYAN, activeforeground=TRON_BLACK, relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=1).pack(side=LEFT, padx=10)
    Button(button_frame, text="Start New Roast", command=on_start, bg=TRON_BLACK, fg=TRON_CYAN, activebackground=TRON_CYAN, activeforeground=TRON_BLACK, relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=1).pack(side=LEFT, padx=10)

# --- Build the Main Roasting UI ---

def setup_main_frame():
    # Helper for TRON button styling
    def create_tron_button(parent, text, command):
        return Button(parent, text=text, command=command, bg=TRON_BLACK, fg=TRON_CYAN, activebackground=TRON_CYAN, activeforeground=TRON_BLACK, relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=1)

    # --- GUI LAYOUT ---
    
    # Top Info Area
    Label(main_frame, text='Roast Name', anchor='w', font=('Helvetica', 9, 'bold'), bg=TRON_BLACK, fg=TRON_WHITE).place(x=10, y=10, height=20, width=130)
    Label(main_frame, textvariable=profiledisplayname, bg=TRON_GRID, fg=TRON_CYAN, anchor='w', font=('Helvetica', 12, 'italic')).place(x=10, y=30, height=25, width=150)

    Label(main_frame, text="TIME", justify=CENTER, font=('Helvetica'), bg=TRON_BLACK, fg=TRON_WHITE).place(x=185, y=10, width=130, height=20)
    global timeText, timer, pattern
    timeText = Label(main_frame, text="00:00:00", font=("Helvetica", 25), bg=TRON_BLACK, fg=TRON_WHITE)
    timeText.place(x=170, y=30, width=160, height=40)
    timer = [0,0,0]
    pattern = '{0:02d}:{1:02d}:{2:02d}'

    
    create_tron_button(main_frame, 'Start', swstart).place(x=170, y=75, height=25, width=50)
    create_tron_button(main_frame, 'Reset', swreset).place(x=225, y=75, height=25, width=50)
    create_tron_button(main_frame, 'Stop', swpause).place(x=280, y=75, height=25, width=60)

    Label(main_frame, text="RoR Window (s):", anchor='e', font=('Helvetica', 9, 'bold'), bg=TRON_BLACK, fg=TRON_WHITE).place(x=370, y=10, height=20, width=120)
    ror_entry = Entry(main_frame, textvariable=ror_time_window, width=5, bg=TRON_GRID, fg=TRON_WHITE, insertbackground=TRON_CYAN, bd=2, relief=FLAT, justify='center')
    ror_entry.place(x=380, y=30, width=100, height=25)

    # PWM Control Area
    Label(main_frame, text='AIR % POWER', anchor='center', bg=TRON_BLACK, fg=TRON_WHITE).place(x=50, y=130, height=20, width=150)
    Label(main_frame, textvariable=bpwmdisp, bg=TRON_BLACK, fg=TRON_CYAN, font=('Helvetica', 60, 'bold')).place(x=50, y=150, height=70, width=150)
    
    Label(main_frame, text='HEAT % POWER', anchor='center', bg=TRON_BLACK, fg=TRON_WHITE).place(x=300, y=130, height=20, width=150)
    Label(main_frame, textvariable=hpwmdisp, bg=TRON_BLACK, fg=TRON_MAGENTA, font=('Helvetica', 60, 'bold')).place(x=300, y=150, height=70, width=150)

    # Set Controls Area
    Label(main_frame, text='SET AIR:', anchor='e', bg=TRON_BLACK, fg=TRON_WHITE).place(x=60, y=240, width=120, height=25)
    global jumptoair, jumptoheat
    jumptoair = Entry(main_frame, bg=TRON_GRID, fg=TRON_WHITE, insertbackground=TRON_CYAN, bd=2, relief=FLAT)
    jumptoair.place(x=185, y=240, width=120, height=25)
    
    Label(main_frame, text='SET HEAT:', anchor='e', bg=TRON_BLACK, fg=TRON_WHITE).place(x=60, y=270, width=120, height=25)
    jumptoheat = Entry(main_frame, bg=TRON_GRID, fg=TRON_WHITE, insertbackground=TRON_CYAN, bd=2, relief=FLAT)
    jumptoheat.place(x=185, y=270, width=120, height=25)

    create_tron_button(main_frame, 'Update\nLevels', go).place(x=315, y=240, height=55, width=75)

    # Temperature Display Area
    Label(main_frame, text="Bean Mass:", anchor='e', font=('Helvetica', 15), bg=TRON_BLACK, fg=TRON_WHITE).place(x=30, y=320, height=60, width=120)
    Label(main_frame, textvariable=t1disp, bg=TRON_BLACK, fg=TRON_CYAN, font=('Helvetica', 40, 'bold')).place(x=160, y=325, height=50, width=115)
    Label(main_frame, text="°F", anchor='w', font=('Helvetica', 15), bg=TRON_BLACK, fg=TRON_WHITE).place(x=280, y=320, height=60, width=40)
    
    Label(main_frame, text="Inlet Air:", anchor='e', font=('Helvetica', 15), bg=TRON_BLACK, fg=TRON_WHITE).place(x=30, y=380, height=60, width=120)
    Label(main_frame, textvariable=t2disp, bg=TRON_BLACK, fg=TRON_MAGENTA, font=('Helvetica', 40, 'bold')).place(x=160, y=385, height=50, width=115)
    Label(main_frame, text="°F", anchor='w', font=('Helvetica', 15), bg=TRON_BLACK, fg=TRON_WHITE).place(x=280, y=380, height=60, width=40)

    # Event Marking Area
    event_frame = Frame(main_frame, bg=TRON_BLACK)
    event_frame.place(x=10, y=450, width=480, height=30)
    Label(event_frame, text="Mark Event:", bg=TRON_BLACK, fg=TRON_WHITE).pack(side=LEFT, padx=(5,10))
    create_tron_button(event_frame, "Start", lambda: mark_event("Start")).pack(side=LEFT, padx=2)
    create_tron_button(event_frame, "Yellowing", lambda: mark_event("Yellowing")).pack(side=LEFT, padx=2)
    create_tron_button(event_frame, "First Crack", lambda: mark_event("First Crack")).pack(side=LEFT, padx=2)
    create_tron_button(event_frame, "End", lambda: mark_event("End")).pack(side=LEFT, padx=2)

    # Bottom Buttons Area
    btn_width, btn_height, pad_x, pad_y = 120, 30, 35, 10
    
    create_tron_button(main_frame, 'New Roast', start_new_roast).place(x=pad_x, y=500, width=btn_width, height=btn_height)
    create_tron_button(main_frame, 'Run Profile', looprunner).place(x=pad_x * 2 + btn_width, y=500, width=btn_width, height=btn_height)
    create_tron_button(main_frame, "Load Profile...", loadit).place(x=pad_x * 3 + btn_width * 2, y=500, width=btn_width, height=btn_height)

    create_tron_button(main_frame, 'Kill All', killall).place(x=pad_x, y=500 + btn_height + pad_y, width=btn_width, height=btn_height)
    create_tron_button(main_frame, "EXIT", close_window).place(x=pad_x * 3 + btn_width * 2, y=500 + btn_height + pad_y, width=btn_width, height=btn_height)
    
    ## CONSOLE OUTPUT ##
    console_output = Text(main_frame, bg=TRON_BLACK, fg=TRON_CYAN, state='disabled', relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=1)
    console_output.place(x=10, y=580, height=110, width=480)
    sys.stdout = TextRedirector(console_output)


# --- MAIN APP START ---
if __name__ == "__main__":
    setup_main_frame()
    setup_startup_frame()
    gui.mainloop()

