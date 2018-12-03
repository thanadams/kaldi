from tkinter import *

blowerpwm = 0
heaterpwm = 0

# GUI
root = Tk()
root.wm_title("KALDI")

# width x height + x_offset + y_offset:
root.geometry("490x430+30+30")

bpwmdisp = StringVar()
bpwmdisp.set(blowerpwm)
hpwmdisp = StringVar()
hpwmdisp.set(heaterpwm)


def setpwm(root, air, heat):
	global blowerpwm
	global heaterpwm

	# air
	blowerpwm = air
	bpwmdisp.set(blowerpwm)
	jumptoair.delete(0, END)

	# heat
	heaterpwm = heat
	hpwmdisp.set(heaterpwm)
	jumptoheat.delete(0, END)
	


def control(root, bkill, hkill):
	global blowerpwm
	global heaterpwm

	# assign the fields
	if jumptoair.get() != '':
		air = int(jumptoair.get())
	else:
		air = blowerpwm

	if jumptoheat.get() != '':
		heat = int(jumptoheat.get())
	else:
		heat = heaterpwm
	
	if bkill == True and heaterpwm == 0:
		setpwm(root, 0, 0)
	elif bkill == True and heaterpwm > 0:
		print('turn off the heater first')
	# initial start - blower first
	# when only the blower starts
	elif (blowerpwm == 0 and heaterpwm == 0) and (air > 0 and heat == 0):
		setpwm(root, air, heat)
	# when both blower and heater start together
	elif (blowerpwm == 0 and heaterpwm == 0) and (air > 0 and heat > 0):
		setpwm(root, air, heat)
	# stuff that's allowed once the blower is running
	elif blowerpwm > 0:
		if hkill == True:
			setpwm(root, blowerpwm, 0)
		elif air == 0 and heaterpwm > 0:
			print('turn off the heater first')
		elif heaterpwm == 0 and bkill == False:
			setpwm(root, air, heat)
		elif heaterpwm > 0 and heat == 0:
			setpwm(root, air, heat)
		elif (air > 0 and heat > 0) and (heaterpwm > 0 and blowerpwm > 0):
			setpwm(root, air, heat)
		else:
			print('inner unsafe state')
	else:
		print('unsafe state')


def close_window(root):
    exit()

def go(root):
	control(root, False, False)

root.bind('<Control-Return>', go)

nr = Label(root, text="KALDI", fg="#B28F4F", font=("Helvetica", 75, "bold"))
nr.place(width=490, height=95)

# duty cycle displays
l_blowlevel = Label(root, text="BLOWER: ")
l_blowlevel.place(x=10, y=135, height=25)

d_blowlevel = Label(root, textvariable=bpwmdisp, bg="blue", fg="white")
d_blowlevel.place(x=70, y=135, height=20)

l_heatlevel = Label(root, text="HEATER: ")
l_heatlevel.place(x=10, y=160, height=25)

d_heatlevel = Label(root, textvariable=hpwmdisp, bg="red", fg="white")
d_heatlevel.place(x=70, y=160, height=20)

# fields to collect the new PWM values
jumptoair = Entry(root, background="#00FFCC")
jumptoair.place(x=185, y=90, width=120, height=25)
jumptoair.focus_set()

jumptoheat = Entry(root, background="#FF3333")
jumptoheat.place(x=185, y=120, width=120, height=25)




# kill blower
def bkill(root):
	control(root, True, False)

kill_blower = Button(root, text="KILL", bg="#000000", fg="#00FFCC", command=lambda: bkill(root))
kill_blower.place(x=310, y=90, width=60, height=25)

# kill heater
def hkill(root):
	control(root, False, True)

kill_heater = Button(root, text="KILL", bg="#000000", fg="#FF3333", command=lambda: hkill(root))
kill_heater.place(x=310, y=120, width=60, height=25)


root.bind('<Control-x>', close_window)

ref = Label(root, text="Set levels: <control + return>\nQuit: <control-x>", justify="left")
ref.place(x=135, y=170, width= 225)

root.mainloop()