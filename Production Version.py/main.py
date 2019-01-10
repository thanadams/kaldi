from tkinter import *
from tkinter import filedialog
import csv
from time import *
from threading import Thread


# this is for the timer
state = False

intervals = []
start = True
profile = False


# >>>>>>>>>>>>>>>>>>>>>>> RPI ONLY
# import RPi.GPIO as GPIO

# GPIO.setmode(GPIO.BOARD)

# # assigning pin 10 - HEATER
# GPIO.setup(10, GPIO.OUT)
# GPIO.output(10, 0)

# # assigning pin 8 - BLOWER
# GPIO.setup(8, GPIO.OUT)
# GPIO.output(8, 0)

# # starting PWM for heater
# heaterpwm = GPIO.PWM(10, 60)
# heaterpwm.start(0)

# # starting PWM for the blower
# blowerpwm = GPIO.PWM(8, 59)
# blowerpwm.start(0)
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>

air_now = 0
heat_now = 0

# GUI
root = Tk()
root.wm_title('KALDI')

# width x height + x_offset + y_offset:
root.geometry('500x350+30+30')

bpwmdisp = StringVar()
bpwmdisp.set(air_now)
hpwmdisp = StringVar()
hpwmdisp.set(heat_now)


# try:

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

def setpwm(root, air, heat):
	global blowerpwm
	global heaterpwm
	global start
	global startint
	global profile
	global heat_now
	global air_now
	
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
		
		##### DEVELOPMENT toggle the two lines below for development on a mac
		blowerpwm = air
		# blowerpwm.ChangeDutyCycle(air)

		air_now = air
		bpwmdisp.set(air_now)
		jumptoair.delete(0, END)

		##### DEVELOPMENT toggle the two lines below for development on a mac
		heaterpwm = heat
		# heaterpwm.ChangeDutyCycle(heat)

		heat_now = heat
		hpwmdisp.set(heat_now)
		jumptoheat.delete(0, END)

	##### DEVELOPMENT 
	#else:
		# blowerpwm.ChangeDutyCycle(air)
		# heaterpwm.ChangeDutyCycle(heat)

def control(root, bkill, hkill):
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
			setpwm(root, newair, newheat)
		elif newair > 0:
			setpwm(root, newair, newheat)
		elif newheat > 0:
			print(msg)
		else:
			print(msg)

	# when the blower is on and the heater is off
	elif air_now > 0 and heat_now == 0:
		if bkill is True:
			setpwm(root, 0, heat_now)
		elif newair > 0 and newheat > 0:
			setpwm(root, newair, newheat)
		elif newair > 0 and newheat != 0:
			setpwm(root, newair, newheat)
		elif newheat > 0 and newair != 0:
			setpwm(root, newair, newheat)
		else:
			print(msg)

	# when both components are on
	elif air_now > 0 and heat_now > 0:
		if hkill is True and bkill is False:
			setpwm(root, air_now, 0)
		elif bkill is True and hkill is True:
			setpwm(root, 0, 0)
		elif newair > 0 and newheat > 0 and bkill is False:
			setpwm(root, newair, newheat)
		elif newair > 0 and newheat != 0 and bkill is False:
			setpwm(root, newair, newheat)
		elif newheat > 0 and newair != 0 and bkill is False:
			setpwm(root, newair, newheat)
		else:
			print(msg)

	else:
		print(msg)
	

def close_window(root):
    control(root, True, True)
    #### DEVELOPMENT
    # GPIO.cleanup()
    exit()

def killall(root):
	swpause()
	control(root, True, True)

def go(root):
	control(root, False, False)

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
    root.after(10, update_timeText)

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

root.bind('<Control-Return>', go)

def b_up(root):
	global air_now
	if air_now > 0:
		new = air_now + 1
		jumptoair.delete(0, END)
		jumptoair.insert(0, int(new))
		control(root, False, False)
	else:
		print('can\'t start that way.')
		jumptoair.delete(0, END)
		jumptoheat.delete(0, END)

def b_down(root):
	global air_now
	if air_now > 0:
		new = air_now - 1
		jumptoair.delete(0, END)
		jumptoair.insert(0, int(new))
		control(root, False, False)
	else:
		print('can\'t start that way.')
		jumptoair.delete(0, END)
		jumptoheat.delete(0, END)

root.bind('<w>', b_up)
root.bind('<s>', b_down)


def h_up(root):
	global heat_now
	if heat_now > 0:
		new = heat_now + 1
		jumptoheat.delete(0, END)
		jumptoheat.insert(0, int(new))
		control(root, False, False)
	else:
		print('can\'t start that way.')
		jumptoair.delete(0, END)
		jumptoheat.delete(0, END)

def h_down(root):
	global heat_now
	if heat_now > 0:
		new = heat_now - 1
		jumptoheat.delete(0, END)
		jumptoheat.insert(0, int(new))
		control(root, False, False)
	else:
		print('can\'t start that way.')
		jumptoair.delete(0, END)
		jumptoheat.delete(0, END)

root.bind('<Up>', h_up)
root.bind('<Down>', h_down)


# duty cycle displays
d_blowlevel = Label(root, textvariable=bpwmdisp, bg='#75DAFF', fg='white', font=('Helvetica', 60, 'bold'))
d_blowlevel.place(x=500-250-125-75, y=10+30+50+10+30, height=70, width=150)

d_heatlevel = Label(root, textvariable=hpwmdisp, bg='red', fg='white', font=('Helvetica', 60, 'bold'))
d_heatlevel.place(x=500-125-75, y=10+30+50+10+30, height=70, width=150)


# PWM LABELS
l_blowlevel = Label(root, text='AIR LEVEL')
l_blowlevel.place(x=500-250-125-(78/2), y=10+50+10+10+30, height=20, width=78)

l_heatlevel = Label(root, text='HEAT LEVEL')
l_heatlevel.place(x=500-125-(78/2), y=10+50+10+10+30, height=20, width=78)


# kill buttons
kill_blower = Button(root, text='KILL', command=lambda: control(root, True, False))
kill_blower.place(x=500-250-125-75, y=120+50-12+10+30, height=25, width=150)

kill_heater = Button(root, text='KILL', command=lambda: control(root, False, True))
kill_heater.place(x=500-125-75, y=120+50-12+10+30, height=25, width=150)


# FIELD COLLECTION LABELS
newblow = Label(root, text='SET AIR:', anchor='e')
newblow.place(x=185-120-5, y=90+75+50+10+30-10, width=120, height=25)

newheat = Label(root, text='SET HEAT:', anchor='e')
newheat.place(x=185-120-5, y=120+75+50+10+30-10, width=120, height=25)


# fields to collect the new PWM values
jumptoair = Entry(root, background='#75DAFF')
jumptoair.place(x=500-250-60, y=90+75+50+10+30-10, width=120, height=25)

jumptoheat = Entry(root, background='red')
jumptoheat.place(x=500-250-60, y=120+75+50+10+30-10, width=120, height=25)




def reset():
	global intervals
	global start
	global profile
	intervals = []
	start = True
	profile = False
	swreset()
	print('intervals reset')

reset_int = Button(root, text='Reset Intervals', command=reset)
reset_int.place(x=10, y=90+75+50+10+30-10+60+15, width=120, height=25)

saveme = Button(root, text="Save as to csv..", command=saveit)
saveme.place(x=500-120-10-120-60+60, y=90+75+50+10+30-10+60+15, width=120, height=25)

# this function opens a saved profile and loads it into blowerinterals/heaterintervals
def loadit():
    global intervals
    with filedialog.askopenfile(mode='r') as infile:
        reader = csv.reader(infile)
        rawimport = list(reader)
        intervals = [list(map(float,rawimport)) for rawimport in rawimport]
    infile.close()
    print("intervals loaded: ")
    print(intervals)

loadme = Button(root, text="Load Profile...", command=loadit)
loadme.place(x=500-120-10, y=90+75+50+10+30-10+60+15, width=120, height=25)

def runit():
        global intervals
        global profile

        profile = True

        ti = len(intervals)

        swstart()

        try:
                for n, i in enumerate(intervals):
                        print(f'interval {n} of {ti}: {i}')
                        setpwm(root, int(round(i[0])), int(round(i[1])))
                        bpwmdisp.set(int(round(i[0])))
                        hpwmdisp.set(int(round(i[1])))
                        sleep(i[2])
        except KeyboardInterrupt:
                pass
        # as a safety measure, make sure both elements are at 0 after profile is finished
        setpwm(root, 0, 0)
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

runme = Button(root, text="Run This Profile", command=looprunner)
runme.place(x=10+120, y=90+75+50+10+30-10+60+15, width=120, height=25) 

directions = '''
set new levels:  control-return
up/down blower:  arrow up/arrow down
up/down heater:  w/s
stop roasting:   control-k
quit:            control-x
'''

#stop watch display label
swDisp = Label(text="TIME", justify=LEFT, font=('Helvetica'))
swDisp.place(x=500-250-(130/2), y=4+10, width=130, height=30)
 
#STOP WATCH DISPLAY
timeText = Label(root, text="00:00:00", font=("Helvetica", 25))
timeText.place(x=500-250-(160/2), y=10+5+5+5+10, width=160, height=40)

global timer
timer = [0, 0, 0]
global pattern
pattern = '{0:02d}:{1:02d}:{2:02d}'

 
#stopwatch buttons
 
startButton = Button(root, text='Start', command=swstart)
startButton.place(x=500-250-(60/2)-65, y=30+35+10, height=25, width=60)

resetButton = Button(root, text='Reset', command=swreset,)
resetButton.place(x=500-250-(60/2), y=30+35+10, height=25, width=60)

stopButton = Button(root, text='Stop', command=swpause)
stopButton.place(x=500-250-(60/2)+65, y=30+35+10, height=25, width=60)
 

## END STOPWATCH ##


root.bind('<Control-x>', close_window)
root.bind('<Control-k>', killall)


update_timeText()
root.mainloop()

# except:
# 	print('a critical error has occurred!')
