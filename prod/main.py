from tkinter import *
from tkinter import filedialog
import csv
from time import *
from threading import Thread
import os


# this is for the timer
state = False

intervals = []
start = True
profile = False

heat_upper_bound = 100
blower_upper_bound = 100

air_now = 0
heat_now = 0

bindings = '''
	set new levels:		[CONTROL] + [RETURN]
	blower up or down:		[ARROW UP] and [ARROW DOWN]
	heater up or down :		[W] and [S]
	stop air and heat:		[CONTROL] + [K]
	exit:  			[CONTROL] + [X]
'''

# >>>>>>>>>>>>>>>>>>>>>>> DEVELOPMENT RPI ONLY
import RPi.GPIO as GPIO

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
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>


# GUI
gui = Tk()
gui.wm_title('KALDI')

# width x height + x_offset + y_offset:
gui.geometry('500x500+30+30')

bpwmdisp = StringVar()
bpwmdisp.set(air_now)
hpwmdisp = StringVar()
hpwmdisp.set(heat_now)

profiledisplayname = StringVar()
profiledisplayname.set('none')


def logit(air, heat, time):
	global intervals
	intervals.append([air, heat, time])
	print(f'new interval {len(intervals)}: {intervals[-1]}')

def saveit():
        global intervals
        with filedialog.asksaveasfile(mode='w') as outfile:
            writer = csv.writer(outfile)
            writer.writerows(intervals)            
        outfile.close()
        print("Successfully printed everything to file!")    

def setpwm(air, heat):
	global blowerpwm
	global heaterpwm
	global start
	global startint
	global profile
	global heat_now
	global air_now
	global heat_upper_bound 
	global heat_lower_bound
	global blower_upper_bound 
	global blower_lower_bound
	
	if air > blower_upper_bound or heat > heat_upper_bound: # or air < blower_lower_bound or heat < heat_lower_bound:
		print('Out of bounds for the blower or heater!')

	else:
		if profile == False:
			if start == True:
				startint = time()
				start = False
				swstart()
			else:
				if air_now == 0 and heat_now == 0:
					logit(air, heat, time() - startint)
				else:
					logit(air_now, heat_now, time() - startint)
				
			startint = time()
			
			# >>>>>>>>>>>>>>>>>>>>>>> DEVELOPEMENT toggle the two lines below for development on a mac
			# blowerpwm = air
			blowerpwm.ChangeDutyCycle(air)

			air_now = air
			bpwmdisp.set(air_now)
			jumptoair.delete(0, END)

			# >>>>>>>>>>>>>>>>>>>>>>> DEVELOPEMENT toggle the two lines below for development on a mac
			# heaterpwm = heat
			heaterpwm.ChangeDutyCycle(heat)

			heat_now = heat
			hpwmdisp.set(heat_now)
			jumptoheat.delete(0, END)

		# >>>>>>>>>>>>>>>>>>>>>>> DEVELOPEMENT these two lines need to be commented to develop on a mac
		else:
			blowerpwm.ChangeDutyCycle(air)
			heaterpwm.ChangeDutyCycle(heat)

def control(bkill, hkill):
	global blowerpwm
	global heaterpwm
	msg = 'unsafe state'

	# assign the fields if they're not 0 or empty
	if jumptoair.get() == '0' or not str.isdigit(jumptoair.get()):
		newair = air_now
	else:
		newair = int(jumptoair.get())
	
	if jumptoheat.get() == '0' or not str.isdigit(jumptoheat.get()):
		newheat = heat_now
	else:
		newheat = int(jumptoheat.get())

	# when both heater and blower are off
	if air_now == 0 and heat_now == 0:
		if newair > 0 and newheat > 0:
			setpwm(newair, newheat)
		elif newair > 0:
			setpwm(newair, newheat)
		elif newheat > 0:
			print(msg)
		else:
			print('unsafe state: both elements are off')

	# when the blower is on and the heater is off
	elif air_now > 0 and heat_now == 0:
		if bkill is True:
			setpwm(0, heat_now)
		elif newair > 0 and newheat > 0:
			setpwm(newair, newheat)
		elif newair > 0 and newheat != 0:
			setpwm(newair, newheat)
		elif newheat > 0 and newair != 0:
			setpwm(newair, newheat)
		elif newair > 0:
			setpwm(newair, newheat)
		else:
			print('unsafe state: blower on and heater off')

	# when both components are on
	elif air_now > 0 and heat_now > 0:
		if hkill is True and bkill is False:
			setpwm(air_now, 0)
		elif bkill is True and hkill is True:
			setpwm(0, 0)
		elif newair > 0 and newheat > 0 and bkill is False:
			setpwm(newair, newheat)
		elif newair > 0 and newheat != 0 and bkill is False:
			setpwm(newair, newheat)
		elif newheat > 0 and newair != 0 and bkill is False:
			setpwm(newair, newheat)
		else:
			print('unsafe state: both elements are on')

	else:
		print(msg)

def update_timeText():
    global state
    global timer
    if (state):
        timer[2] += 1       
        if (timer[2] >= 60):
            timer[2] = 0
            timer[1] += 1
        if (timer[1] >= 60):
            timer[0] += 1
            timer[1] = 0
        timeString = pattern.format(timer[0], timer[1], timer[2])
        timeText.configure(text=timeString)
    gui.after(10, update_timeText)

def swstart():
    global state
    state = True

def swpause():
    global state
    state = False

def swreset():
    global timer
    timer = [0, 0, 0]
    timeText.configure(text='00:00:00')

# this function opens a saved profile and loads it into blowerinterals/heaterintervals
def loadit():
    global intervals
    with filedialog.askopenfile(mode='r') as infile:
        reader = csv.reader(infile)
        rawimport = list(reader)
        intervals = [list(map(float,rawimport)) for rawimport in rawimport]
        profiledisplayname.set(os.path.basename(infile.name))
        profile_name = os.path.basename(infile.name)

    infile.close()
    print(f'FILENAME: {profile_name}')
    print("intervals loaded: ")
    print(intervals)

def runit():
        global intervals
        global profile

        profile = True

        ti = len(intervals)

        swstart()

        try:
                for n, i in enumerate(intervals):
                        print(f'interval {n} of {ti}: {i}')
                        setpwm(int(round(i[0])), int(round(i[1])))
                        bpwmdisp.set(int(round(i[0])))
                        hpwmdisp.set(int(round(i[1])))
                        sleep(i[2])
        except KeyboardInterrupt:
                pass
        # as a safety measure, make sure both elements are at 0 after profile is finished
        setpwm(0, 0)
        profile = False
        swpause()
        print('Done running the thing!')
        hpwmdisp.set(0)
        bpwmdisp.set(0)
        jumptoair.delete(0, END)
        jumptoheat.delete(0, END)
        jumptoair.focus_set()

def looprunner():
        runner_thread = Thread(target=runit)
        runner_thread.start()

def reset():
	global intervals
	global start
	global profile
	intervals = []
	start = True
	profile = False
	swreset()
	print('intervals reset')
	profiledisplayname.set('none')

# These are the key bindings and their associated functions
def close_window(gui):
    control(True, True)
    # >>>>>>>>>>>>>>>>>>>>>>> DEVELOPEMENT the 1 line blow needs to be commented out
    GPIO.cleanup()
    exit()

def killall(gui):
	swpause()
	control(True, True)

def go(gui):
	control(False, False)
	# I couldn't get the key binding to work with the control function directly, so I made this.

def b_up(gui):
	global air_now
	if air_now > 0:
		new = air_now + 1
		jumptoair.delete(0, END)
		jumptoair.insert(0, int(new))
		control(False, False)
	else:
		print('can\'t start that way.')
		jumptoair.delete(0, END)
		jumptoheat.delete(0, END)

def b_down(gui):
	global air_now
	if air_now > 0:
		new = air_now - 1
		jumptoair.delete(0, END)
		jumptoair.insert(0, int(new))
		control(False, False)
	else:
		print('can\'t start that way.')
		jumptoair.delete(0, END)
		jumptoheat.delete(0, END)

def h_up(gui):
	global heat_now
	if heat_now > 0:
		new = heat_now + 1
		jumptoheat.delete(0, END)
		jumptoheat.insert(0, int(new))
		control(False, False)
	else:
		print('can\'t start that way.')
		jumptoair.delete(0, END)
		jumptoheat.delete(0, END)

def h_down(gui):
	global heat_now
	if heat_now > 0:
		new = heat_now - 1
		jumptoheat.delete(0, END)
		jumptoheat.insert(0, int(new))
		control(False, False)
	else:
		print('can\'t start that way.')
		jumptoair.delete(0, END)
		jumptoheat.delete(0, END)

gui.bind('<Up>', h_up)
gui.bind('<Down>', h_down)
gui.bind('<w>', b_up)
gui.bind('<s>', b_down)
gui.bind('<Control-Return>', go)
gui.bind('<Control-x>', close_window)
gui.bind('<Control-k>', killall)


# PWM LABELS
l_blowlevel = Label(text='AIR % POWER', anchor='center')
l_blowlevel.place(x=50, y=10+50+10+10+30, height=20, width=150)

l_heatlevel = Label(text='HEAT % POWER', anchor='center')
l_heatlevel.place(x=300, y=10+50+10+10+30, height=20, width=150)


# duty cycle displays
d_blowlevel = Label(textvariable=bpwmdisp, bg='#75DAFF', fg='white', font=('Helvetica', 60, 'bold'))
d_blowlevel.place(x=50, y=10+30+50+10+30, height=70, width=150)

d_heatlevel = Label(textvariable=hpwmdisp, bg='red', fg='white', font=('Helvetica', 60, 'bold'))
d_heatlevel.place(x=300, y=10+30+50+10+30, height=70, width=150)


# profile name field
l_blowlevel = Label(text='LOADED PROFILE', anchor='center', font=('Helvetica', 9, 'bold'))
l_blowlevel.place(x=5, y=5, height=20, width=130)

d_profilename = Label(textvariable=profiledisplayname, bg='#fff0ba', fg='black', anchor='center', font=('Helvetica', 12, 'italic'))
d_profilename.place(x=5, y=5+20+5+20-25, height=20, width=130)



# kill buttons
kill_blower = Button(text='KILL', command=lambda: control(True, False))
kill_blower.place(x=500-250-125-75, y=120+50-12+10+30, height=25, width=150)

kill_heater = Button(text='KILL', command=lambda: control(False, True))
kill_heater.place(x=500-125-75, y=120+50-12+10+30, height=25, width=150)



# FIELD COLLECTION LABELS
newblow = Label(text='SET AIR:', anchor='e')
newblow.place(x=185-120-5, y=90+75+50+10+30-10, width=120, height=25)

newheat = Label(text='SET HEAT:', anchor='e')
newheat.place(x=185-120-5, y=120+75+50+10+30-10, width=120, height=25)



# fields to collect the new PWM values
jumptoair = Entry(background='#75DAFF')
jumptoair.place(x=500-250-60, y=90+75+50+10+30-10, width=120, height=25)

jumptoheat = Entry(background='red')
jumptoheat.place(x=500-250-60, y=120+75+50+10+30-10, width=120, height=25)


# label for the keymappings
mappings = Label(text=bindings, anchor='center', font=('Helvetica', 9, 'italic'), justify=LEFT)
mappings.place(x=15, y=335, height=75, width=420)


# button to set both
set_levels = Button(text='update\nlevels', command=lambda:control(False, False))
set_levels.place(x=315, y=245, height=55, width=75)

reset_int = Button(text='Reset Intervals', command=reset)
reset_int.place(x=10, y=445, width=120, height=25)

kill_both_elements = Button(text='Kill heat and air', command=lambda:killall(gui))
kill_both_elements.place(x=10, y=445+26, width=120, height=25)

saveme = Button(text="Save as to csv..", command=saveit)
saveme.place(x=250, y=445, width=120, height=25)

loadme = Button(text="Load Profile...", command=loadit)
loadme.place(x=370, y=445, width=120, height=25)

closewindow = Button(text="EXIT", command=lambda:close_window(gui))
closewindow.place(x=370, y=445+26, width=120, height=25)

runme = Button(text="Run this profile", command=looprunner)
runme.place(x=130, y=445, width=120, height=25) 




## START STOPWATCH ##
global timer
global pattern
timer = [0, 0, 0]
pattern = '{0:02d}:{1:02d}:{2:02d}'

#stop watch display label
swDisp = Label(text="TIME", justify=LEFT, font=('Helvetica'))
swDisp.place(x=500-250-(130/2), y=4+10, width=130, height=30)
 
#stop watch display
timeText = Label(text="00:00:00", font=("Helvetica", 25))
timeText.place(x=500-250-(160/2), y=10+5+5+5+10, width=160, height=40)
 
#stopwatch buttons
startButton = Button(text='Start', command=swstart)
startButton.place(x=500-250-(60/2)-65, y=30+35+10, height=25, width=60)

resetButton = Button(text='Reset', command=swreset)
resetButton.place(x=500-250-(60/2), y=30+35+10, height=25, width=60)

stopButton = Button(text='Stop', command=swpause)
stopButton.place(x=500-250-(60/2)+65, y=30+35+10, height=25, width=60)
## END STOPWATCH ##



update_timeText()
gui.mainloop()