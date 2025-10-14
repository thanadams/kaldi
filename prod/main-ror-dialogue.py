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

# Configure the temp sensor
errmsg = YRefParam()
if YAPI.RegisterHub("127.0.0.1", errmsg) != YAPI.SUCCESS:
    sys.exit("init error" + errmsg.value)

sensor1 = YTemperature.FindTemperature('THRMCPL1-57DE2.temperature1')
sensor2 = YTemperature.FindTemperature('THRMCPL1-57DE2.temperature2')

if not (sensor1.isOnline() and sensor2.isOnline()):
    sys.exit('Error: Thermocouple sensors not found. Please check connections.')

# this is for the timer state
state = False

# Variables to hold the after() job IDs for clean shutdown
after_id_update_graph = None
after_id_update_timeText = None
after_id_poll_sensors = None

# Using deque for memory efficiency, stores the last 10 minutes of data (600 seconds)
temps = collections.deque(maxlen=600)
ror_history = collections.deque(maxlen=600)
intervals = []
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
gui.geometry("500x500+30+30") 
gui.configure(bg=TRON_BLACK)

# Create frames for swapping between startup and main UI
startup_frame = Frame(gui, bg=TRON_BLACK)
main_frame = Frame(gui, bg=TRON_BLACK)

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

def create_graph_window():
    """Creates a new window for the live RoR graph with TRON styling."""
    global fig
    graph_window = Toplevel(gui)
    graph_window.wm_title("Rate of Rise (RoR)")
    graph_window.geometry("600x400+550+30")
    graph_window.configure(bg=TRON_BLACK)

    fig = plt.Figure(figsize=(5, 4), dpi=100)
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
    
    ax.set_title("Rate of Rise", color=TRON_WHITE)
    ax.set_xlabel("Time (seconds)", color=TRON_WHITE)
    ax.set_ylabel("Temp Change (°F / sec)", color=TRON_WHITE)
    
    ax.grid(True, color=TRON_GRID)
    ax.tick_params(axis='x', colors=TRON_WHITE)
    ax.tick_params(axis='y', colors=TRON_WHITE)
    
    for spine in ax.spines.values():
        spine.set_edgecolor(TRON_CYAN)

    canvas.draw()
    
    after_id_update_graph = gui.after(1000, update_graph, ax, canvas)

def tempit():
    """Reads sensor data, updates display, and calculates RoR."""
    global temps, ror_history, timer
    ch1 = round(sensor1.get_currentValue())
    ch2 = round(sensor2.get_currentValue())
    
    t1disp.set(ch2) 
    t2disp.set(ch1) 
    
    timetosend = datetime.datetime.now().strftime("%H%M%S")
    
    temps.append([ch2, ch1, timetosend])

    if len(temps) > 1:
        ror = temps[-1][0] - temps[-2][0]
        current_time_seconds = timer[0] * 3600 + timer[1] * 60 + timer[2]
        ror_history.append((current_time_seconds, ror))

    print(f'CHANNEL1: {ch1} CHANNEL2: {ch2}')

def poll_sensors():
    """If the timer is running, poll the sensors."""
    global after_id_poll_sensors
    if state:
        tempit()
    after_id_poll_sensors = gui.after(1000, poll_sensors)

def logit(air, heat, time_interval, time_of_log):
    global intervals
    intervals.append([air, heat, time_interval, time_of_log])
    print(f'new interval {len(intervals)}: {intervals[-1]}')

def saveit():
    """Saves the intervals, temps, and RoR graph to files using the roast_name."""
    global roast_name, fig, intervals, temps

    if not roast_name or not temps:
        print("Roast name not set or no temperature data to save.")
        return

    save_dir = "/share/profiles/"
    os.makedirs(save_dir, exist_ok=True)

    today_date = datetime.datetime.now().strftime('%Y-%m-%d')
    base_filename = f"{today_date}_{roast_name}"

    intervals_path = os.path.join(save_dir, f"{base_filename}-intervals.csv")
    try:
        with open(intervals_path, 'w', newline='') as outfile:
            writer = csv.writer(outfile)
            writer.writerows(intervals)
        print(f"Intervals saved to {intervals_path}")
    except Exception as e:
        print(f"Error saving intervals: {e}")

    temps_path = os.path.join(save_dir, f"{base_filename}-temps.csv")
    try:
        with open(temps_path, 'w', newline='') as outfile:
            writer = csv.writer(outfile)
            writer.writerows(list(temps))
        print(f"Temperatures saved to {temps_path}")
    except Exception as e:
        print(f"Error saving temps: {e}")
    
    if fig:
        graph_path = os.path.join(save_dir, f"{base_filename}-ror-curve.jpg")
        try:
            # Add facecolor and bbox_inches to ensure the TRON theme and all labels are saved correctly.
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
    global state
    state = True

def swpause():
    global state
    state = False

def swreset():
    global timer, temps, ror_history
    swpause()
    timer = [0, 0, 0]
    timeText.configure(text='00:00:00')
    temps.clear()
    ror_history.clear()

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
    else:
        roast_name = f"untitled-roast-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    gui.wm_title(f'KALDI - {roast_name}')
    print(f"Started new roast: {roast_name}")

def close_window(event=None):
    global after_id_update_graph, after_id_update_timeText, after_id_poll_sensors
    
    if after_id_update_graph:
        gui.after_cancel(after_id_update_graph)
    if after_id_update_timeText:
        gui.after_cancel(after_id_update_timeText)
    if after_id_poll_sensors:
        gui.after_cancel(after_id_poll_sensors)
    
    saveit()
    control(bkill=True, hkill=True)
    GPIO.cleanup()
    gui.destroy()

def killall(event=None):
    global profile_running
    profile_running = False
    swpause()
    saveit()
    control(bkill=True, hkill=True)

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
    poll_sensors()

# --- Build the Startup UI ---

def setup_startup_frame():
    startup_frame.pack(pady=150)
    Label(startup_frame, text="Start a new roast or load an existing profile.", font=("Helvetica", 14), bg=TRON_BLACK, fg=TRON_WHITE).pack(pady=20)
    
    name_frame = Frame(startup_frame, bg=TRON_BLACK)
    Label(name_frame, text="New Roast Name:", bg=TRON_BLACK, fg=TRON_CYAN).pack(side=LEFT, padx=5)
    name_entry = Entry(name_frame, width=20, bg=TRON_GRID, fg=TRON_WHITE, insertbackground=TRON_CYAN, bd=2, relief=FLAT)
    name_entry.pack(side=LEFT)
    name_frame.pack(pady=10)
    name_entry.focus_set()

    def on_start():
        global roast_name
        roast_name = name_entry.get()
        if not roast_name:
            roast_name = f"untitled-roast-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        transition_to_main_app()

    def on_load():
        if loadit():
            transition_to_main_app()

    button_frame = Frame(startup_frame, bg=TRON_BLACK)
    button_frame.pack(pady=20)
    
    Button(button_frame, text="Start New Roast", command=on_start, bg=TRON_BLACK, fg=TRON_CYAN, activebackground=TRON_CYAN, activeforeground=TRON_BLACK, relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=1).pack(side=LEFT, padx=10)
    Button(button_frame, text="Load Profile", command=on_load, bg=TRON_BLACK, fg=TRON_CYAN, activebackground=TRON_CYAN, activeforeground=TRON_BLACK, relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=1).pack(side=LEFT, padx=10)

# --- Build the Main Roasting UI ---

def setup_main_frame():
    # Helper for TRON button styling
    def create_tron_button(parent, text, command):
        return Button(parent, text=text, command=command, bg=TRON_BLACK, fg=TRON_CYAN, activebackground=TRON_CYAN, activeforeground=TRON_BLACK, relief=FLAT, highlightbackground=TRON_CYAN, highlightthickness=1)

    # --- GUI LAYOUT ---
    # PWM LABELS
    Label(main_frame, text='AIR % POWER', anchor='center', bg=TRON_BLACK, fg=TRON_WHITE).place(x=50, y=120, height=20, width=150)
    Label(main_frame, text='HEAT % POWER', anchor='center', bg=TRON_BLACK, fg=TRON_WHITE).place(x=300, y=120, height=20, width=150)

    # duty cycle displays
    Label(main_frame, textvariable=bpwmdisp, bg=TRON_BLACK, fg=TRON_CYAN, font=('Helvetica', 60, 'bold')).place(x=50, y=140, height=70, width=150)
    Label(main_frame, textvariable=hpwmdisp, bg=TRON_BLACK, fg=TRON_MAGENTA, font=('Helvetica', 60, 'bold')).place(x=300, y=140, height=70, width=150)

    # profile name field
    Label(main_frame, text='LOADED PROFILE', anchor='center', font=('Helvetica', 9, 'bold'), bg=TRON_BLACK, fg=TRON_WHITE).place(x=5, y=5, height=20, width=130)
    Label(main_frame, textvariable=profiledisplayname, bg=TRON_GRID, fg=TRON_CYAN, anchor='center', font=('Helvetica', 12, 'italic')).place(x=5, y=25, height=20, width=130)

    # FIELD COLLECTION LABELS
    Label(main_frame, text='SET AIR:', anchor='e', bg=TRON_BLACK, fg=TRON_WHITE).place(x=60, y=220, width=120, height=25)
    Label(main_frame, text='SET HEAT:', anchor='e', bg=TRON_BLACK, fg=TRON_WHITE).place(x=60, y=250, width=120, height=25)

    # fields to collect the new PWM values
    global jumptoair, jumptoheat
    jumptoair = Entry(main_frame, bg=TRON_GRID, fg=TRON_WHITE, insertbackground=TRON_CYAN, bd=2, relief=FLAT)
    jumptoair.place(x=185, y=220, width=120, height=25)
    jumptoheat = Entry(main_frame, bg=TRON_GRID, fg=TRON_WHITE, insertbackground=TRON_CYAN, bd=2, relief=FLAT)
    jumptoheat.place(x=185, y=250, width=120, height=25)

    # button to set both
    create_tron_button(main_frame, 'Update\nLevels', go).place(x=315, y=220, height=55, width=75)

    # temperature displays
    Label(main_frame, text="Bean Mass:", anchor='e', font=('Helvetica', 15), bg=TRON_BLACK, fg=TRON_WHITE).place(x=30, y=300, height=60, width=120)
    Label(main_frame, textvariable=t1disp, bg=TRON_BLACK, fg=TRON_CYAN, font=('Helvetica', 40, 'bold')).place(x=160, y=305, height=50, width=115)
    Label(main_frame, text="°F", anchor='w', font=('Helvetica', 15), bg=TRON_BLACK, fg=TRON_WHITE).place(x=280, y=300, height=60, width=40)
    Label(main_frame, text="Inlet Air:", anchor='e', font=('Helvetica', 15), bg=TRON_BLACK, fg=TRON_WHITE).place(x=30, y=360, height=60, width=120)
    Label(main_frame, textvariable=t2disp, bg=TRON_BLACK, fg=TRON_MAGENTA, font=('Helvetica', 40, 'bold')).place(x=160, y=365, height=50, width=115)
    Label(main_frame, text="°F", anchor='w', font=('Helvetica', 15), bg=TRON_BLACK, fg=TRON_WHITE).place(x=280, y=360, height=60, width=40)

    # buttons along bottom
    create_tron_button(main_frame, 'New Roast', start_new_roast).place(x=10, y=445, width=120, height=25)
    create_tron_button(main_frame, 'Kill All', killall).place(x=10, y=445+26, width=120, height=25)
    create_tron_button(main_frame, "Load Profile...", loadit).place(x=370, y=445, width=120, height=25)
    create_tron_button(main_frame, "EXIT", close_window).place(x=370, y=445+26, width=120, height=25)
    create_tron_button(main_frame, "Run Profile", looprunner).place(x=130, y=445, width=120, height=25)

    ## START STOPWATCH ##
    global timer, pattern, timeText
    timer = [0, 0, 0]
    pattern = '{0:02d}:{1:02d}:{2:02d}'

    Label(main_frame, text="TIME", justify=LEFT, font=('Helvetica'), bg=TRON_BLACK, fg=TRON_WHITE).place(x=185, y=5, width=130, height=30)
    timeText = Label(main_frame, text="00:00:00", font=("Helvetica", 25), bg=TRON_BLACK, fg=TRON_WHITE)
    timeText.place(x=170, y=30, width=160, height=40)
    
    create_tron_button(main_frame, 'Start', swstart).place(x=170, y=75, height=25, width=50)
    create_tron_button(main_frame, 'Reset', swreset).place(x=225, y=75, height=25, width=50)
    create_tron_button(main_frame, 'Stop', swpause).place(x=280, y=75, height=25, width=60)
    ## END STOPWATCH ##

# --- MAIN APP START ---
if __name__ == "__main__":
    setup_main_frame()
    setup_startup_frame()
    gui.mainloop()

