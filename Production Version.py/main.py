from tkinter import *
from tkinter import filedialog
import csv
from time import *
from threading import Thread

# this is for the timer
state = False

# global variables we need all functions to be aware of
blowerpwm = 0
heaterpwm = 0
intervals = []
start = True
profile = False


# GUI
root = Tk()
root.wm_title('KALDI')

# width x height + x_offset + y_offset:
root.geometry('500x500+30+30')

bpwmdisp = StringVar()
bpwmdisp.set(blowerpwm)
hpwmdisp = StringVar()
hpwmdisp.set(heaterpwm)


try:

	def logit(air, heat, time):
		global intervals
		intervals.append([air, heat, time])
		for i, n in enumerate(intervals):
			print(f'interval {i}: {n}')

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
		
		if profile == False:
			if start == True:
				startint = time()
				start = False
				swstart()
			else:
				logit(air, heat, time() - startint)
				startint = time()

		# change air
		blowerpwm = air
		bpwmdisp.set(blowerpwm)
		jumptoair.delete(0, END)

		# change heat
		heaterpwm = heat
		hpwmdisp.set(heaterpwm)
		jumptoheat.delete(0, END)
		

	def control(root, bkill, hkill):
		global blowerpwm
		global heaterpwm
		msg = 'unsafe state'

		# assign the fields if they're not 0 or empty
		if jumptoair.get() == '0' or not str.isdigit(jumptoair.get()):
			newair = blowerpwm
		else:
			newair = int(jumptoair.get())
		
		if jumptoheat.get() == '0' or not str.isdigit(jumptoheat.get()):
			newheat = heaterpwm
		else:
			newheat = int(jumptoheat.get())

		# when both heater and blower are off
		if blowerpwm == 0 and heaterpwm == 0:
			if newair > 0 and newheat > 0:
				setpwm(root, newair, newheat)
			elif newair > 0:
				setpwm(root, newair, newheat)
			elif newheat > 0:
				print(msg)
			else:
				print(msg)

		# when the blower is on and the heater is off
		elif blowerpwm > 0 and heaterpwm == 0:
			if bkill is True:
				setpwm(root, 0, heaterpwm)
			elif newair > 0 and newheat > 0:
				setpwm(root, newair, newheat)
			elif newair > 0 and newheat != 0:
				setpwm(root, newair, newheat)
			elif newheat > 0 and newair != 0:
				setpwm(root, newair, newheat)
			else:
				print(msg)

		# when both components are on
		elif blowerpwm > 0 and heaterpwm > 0:
			if hkill is True and bkill is False:
				setpwm(root, blowerpwm, 0)
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
	    print(state)


	def swpause():
	    global state
	    state = False


	def swreset():
	    global timer
	    timer = [0, 0, 0]
	    timeText.configure(text='00:00:00')

	root.bind('<Control-Return>', go)

	nr = Label(root, text='KALDI', fg='#000000', font=('Helvetica', 75, 'bold'))
	nr.place(width=490, height=95)

	# duty cycle displays
	l_blowlevel = Label(root, text='BLOWER: ')
	l_blowlevel.place(x=10, y=135, height=25)

	d_blowlevel = Label(root, textvariable=bpwmdisp, bg='blue', fg='white')
	d_blowlevel.place(x=70, y=135, height=20)

	l_heatlevel = Label(root, text='HEATER: ')
	l_heatlevel.place(x=10, y=160, height=25)

	d_heatlevel = Label(root, textvariable=hpwmdisp, bg='red', fg='white')
	d_heatlevel.place(x=70, y=160, height=20)

	# fields to collect the new PWM values
	jumptoair = Entry(root, background='#75DAFF')
	jumptoair.place(x=185, y=90, width=120, height=25)
	jumptoair.focus_set()

	jumptoheat = Entry(root, background='red')
	jumptoheat.place(x=185, y=120, width=120, height=25)

	kill_blower = Button(root, text='KILL', bg='#000000', fg='#00FFCC', command=lambda: control(root, True, False))
	kill_blower.place(x=310, y=90, width=60, height=25)

	kill_heater = Button(root, text='KILL', bg='#000000', fg='#FF3333', command=lambda: control(root, False, True))
	kill_heater.place(x=310, y=120, width=60, height=25)

	def reset():
		global intervals
		global start
		global profile
		intervals = []
		start = True
		profile = False
		swreset()
		print('intervals reset')

	reset_int = Button(root, text='Reset Intervals', bg='#000000', fg='#FF3333', command=reset)
	reset_int.place(x=310, y=160, width=120, height=25)

	saveme = Button(root, text="Save as to csv..", bg="#FFFFFF", fg="#000000",command=saveit)
	saveme.place(x=310, y=190, width=120, height=25)

	# this function opens a saved profile and loads it into blowerinterals/heaterintervals
	def loadit():
	    global intervals
	    # open a file using askopenfile and storing it in "outfile" - LEFT OFF HERE
	    with filedialog.askopenfile(mode='r') as infile:
	        reader = csv.reader(infile)
	        rawimport = list(reader)
	        intervals = [list(map(float,rawimport)) for rawimport in rawimport]
	    infile.close()
	    print("intervals loaded: ")
	    print(intervals)

	loadme = Button(root, text="Load Profile...", bg="#FFFFFF", fg="#000000",command=loadit)
	loadme.place(x=360, y=325, width=120, height=25)

	def runit():
			global intervals
			global profile

			profile = True

			ti = len(intervals)

			swstart()
			for n, i in enumerate(intervals):
				print(f'interval {n} of {ti}: {i}')

				jumptoair.delete(0, END)	
				jumptoair.insert(0, int(round(i[0])))

				jumptoheat.delete(0, END)
				jumptoheat.insert(0, int(round(i[1])))

				if int(round(i[0])) != 0 and int(round(i[1])) != 0:
					control(root, False, False)
				elif int(round(i[0])) != 0 and int(round(i[1])) == 0:
					control(root, False, True)
				elif int(round(i[0])) == 0 and int(round(i[1])) == 0:
					control(root, True, True)
				else:
					continue

				sleep(i[2])
	        
			swpause()
			profile = False
			print('Done running the thing!')

			jumptoair.delete(0, END)
			jumptoheat.delete(0, END)
			jumptoair.focus_set()

	def looprunner():
	        runner_thread = Thread(target=runit)
	        runner_thread.start()

	runme = Button(root, text="Run This Profile", bg="#FFFFFF", fg="#000000",command=looprunner)
	runme.place(x=360, y=355, width=120, height=25) 

	directions = '''
	set new levels:  control-return
	quit:            control-x
	'''

	ref = Label(root, text=directions, justify='left', font=('courier'))
	ref.place(y=250, width=500)

	#stop watch display label
	swDisp = Label(text="STOPWATCH:", justify=LEFT, anchor=W)
	swDisp.place(x=10, y=360, width=120, height=25)
	 
	#STOP WATCH DISPLAY
	timeText = Label(root, text="00:00:00", bg="white", font=("Helvetica", 30), justify=LEFT, anchor=W)
	timeText.place(x=10, y=360, width=185, height=50)

	global timer
	timer = [0, 0, 0]
	global pattern
	pattern = '{0:02d}:{1:02d}:{2:02d}'

	 
	#stopwatch buttons
	 
	startButton = Button(root, text='Start', command=swstart, bg="#00CC66")
	startButton.place(x=135, y=360, height=50, width=60)

	stopButton = Button(root, text='Stop', command=swpause, bg="#CC0000")
	stopButton.place(x=265, y=360, height=50, width=60)

	resetButton = Button(root, text='Reset', command=swreset, bg="#FFFF00")
	resetButton.place(x=200, y=360, height=50, width=60)
	 

	## END STOPWATCH ##


	root.bind('<Control-x>', close_window)
	root.bind('<Control-k>', killall)


	update_timeText()
	root.mainloop()

except:
	print('a critical error has occurred!')