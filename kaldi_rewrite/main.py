import time
from threading import Thread
from tkinter import *
import tkinter
import tkinter.filedialog
import csv

# import RPi.GPIO as GPIO
# GPIO.setmode(GPIO.BOARD)

# # assigning pin 12 - HEATER
# GPIO.setup(12, GPIO.OUT)
# GPIO.output(12, 0)

# # assigning pin 22 - BLOWER
# GPIO.setup(22, GPIO.OUT)
# GPIO.output(22, 0)

# # starting PWM for heater
# heaterpwm = GPIO.PWM(12, 60)
# heaterpwm.start(0)

# # starting PWM for the blower
# blowerpwm = GPIO.PWM(22, 58)
# blowerpwm.start(0)

heaterpwm = 0
blowerpwm = 0

blowerintervals = []
heaterintervals = []
blowernumint = 1
heaternumint = 1


"""first thing: this module calls the instance to record the intervals of the blower and heater"""


class recTime():
    def __init__(self, name):
        self.name = name
        # this is a temp variable that needs to be unique to the element
        appendme = []
        self.appendme = appendme
        # this is the variable used to figure out if its the initial startup for the element
        initial = True
        self.initial = initial
        # this is the interval counter for each element
        interval = 1
        self.interval = interval
        # here are the two time variables we can't have being shared:
        initialized = 0
        self.initialized = initialized
        elapsed = 0
        self.elapsed = elapsed
        # lastly, two lists where the intervals will be stored
        global heaterintervals
        global blowerintervals
        global heaternumint
        global blowernumint

    def logit(self, name, finalkill):
        global heaterintervals
        global blowerintervals
        # finalkill is passed as True when control-k is activated, or the kill buttons are used
        # this way a number is not added the the interval count
        self.finalkill = finalkill
        # if its the the initialization, then log the start time, set interval to 1 and turn off initial
        if self.initial == True:
            self.initialized = time.time()
            self.initial = False
            print("          %s logging started at: %d" % (self.name, time.time()))
            print("          THIS IS INTERVAL: %d" % self.interval)
        # if its the final kill (kill buttons or control-k) then don't add an interval number
        elif self.finalkill == True:
            self.elapsed = time.time() - self.initialized
            self.initialized = time.time()
            print("          THIS IS INTERVAL: %d" % self.interval)
            # add the interval time and PWM for either the blower of heater to the appropriate interval
            if self.name == "blower":
                self.appendme = [self.elapsed, blower.pwm]
                blowerintervals.append(self.appendme)
                print(blowerintervals)
            elif self.name == "heater":
                self.appendme = [self.elapsed, heater.pwm]
                heaterintervals.append(self.appendme)
                print(heaterintervals)
        # if its NOT initial startup, or the final kill, subtract initial time, and reset it to current time
        elif self.initial == False:
            self.elapsed = time.time() - self.initialized
            self.initialized = time.time()
            print("          THIS IS INTERVAL: %d" % self.interval)

            
            # THIS IS THE PIECE THAT ACTUALLY ASSEMBLES THE INTERVAL LOG
            if self.name == "blower":
                # check to see if the PWM changed, if it didn't - then copy the prior pwm with the elapsed time
                if blower.pwm == blower.priorpwm:
                    self.appendme = [self.elapsed, blower.pwm]
                    blowerintervals.append(self.appendme)
                    print(blowerintervals)
                    self.interval = self.interval + 1
                    blowernumint = self.interval
                else:
                    # do what you'd normally do since the pwm is being changed
                    self.appendme = [self.elapsed, blower.priorpwm]
                    blowerintervals.append(self.appendme)
                    print(blowerintervals)
                    self.interval = self.interval + 1
                    blowernumint = self.interval
            elif self.name == "heater":
                if heater.pwm == heater.priorpwm:
                    self.appendme = [self.elapsed, heater.pwm]
                    heaterintervals.append(self.appendme)
                    print(heaterintervals)
                    self.interval = self.interval + 1
                    heaternumint = self.interval
                else:
                    self.appendme = [self.elapsed, heater.priorpwm]
                    heaterintervals.append(self.appendme)
                    print(heaterintervals)
                    self.interval = self.interval + 1
                    heaternumint = self.interval 
                
    def reset(self):
        self.initial = True
        global heaterintervals
        global blowerintervals
        blowerintervals = []
        heaterintervals = []
        global blowernumint
        global heaternumint
        print("intervals have been cleared")
        
    # this function prints the intervals to screen for the uset to look at before saving them
    def printit(self, element):
        global intLIB
        self.element = element
        if self.element == "heater":
            print(heaterintervals)
        elif self.element == "blower":
            print(blowerintervals)

        print("last but not least, intLIB: ")
        print (intLIB)


    
# modDUTY is the object that runs the instances for the blower and heater, this the the nuts and bolts of controlling the heater and blower
class modDuty():
    def __init__(self, name, highTh, lowTh, pwm=0):
        # these variables are passed to the instance of modDuty and reassigned within the instance
        self.name = name
        self.pwm = pwm
        self.started = False
        self.highTh = highTh
        self.lowTh = lowTh
        self.priorpwm = 0
        global GPIO
        global blowerpwm
        global heaterpwm
        global datetime

    # jumpstart uses this to change the PWM
    def NewDuty(self, name, PWM):
        PWM = int(PWM)
        if name == "blower":
            blowerpwm.ChangeDutyCycle(PWM)
        elif name == "heater":
            heaterpwm.ChangeDutyCycle(PWM)
    
    # this little guy tells logit to run for the blower and heater - it's inserted after all of the important events
    def lognow(self):
        if self.name == "blower":
            blowerlog.logit(self.name, False)
        else:
            heaterlog.logit(self.name, False)

    # this function is for when the control-k keystroke is activated, it kills and does not increase the interval number
    def lognowthenkill(self):
        if self.name == "blower":
            blowerlog.logit(self.name, True)
        else:
            heaterlog.logit(self.name, True)
            
        # this is the chunk of code that changes the displayed levels
        if self.name == "blower":
            global bpwmdisp
            bpwmdisp.set("--")            
        elif self.name == "heater":
            global hpwmdisp
            hpwmdisp.set("--")
    
    # turns OFF the element (heater or blower) in question when the kill button is pressed
    def kill(self):
        if self.name == "blower" and heater.started == True:
            print("KILL HEATER FIRST!")
        elif self.name == "blower" and heater.started == False:
            self.NewDuty(self.name, 0)
            print (self.name, "%s has been fully turned off." % self.name)
            self.started = False
        elif self.name != "blower":
            self.NewDuty(self.name, 0)
            print ("%s has been fully turned off." % self.name)
            self.started = False
        # this is the chunk of code that changes the displayed levels
        if self.name == "blower":
            global bpwmdisp
            bpwmdisp.set('--')            
        elif self.name == "heater":
            global hpwmdisp
            hpwmdisp.set('--')
    
    # jumps the element directly to ANY PWM
    def startjump(self, jumpto):
        if self.pwm == 0:
            self.priorpwm = jumpto
        else:
            self.priorpwm = self.pwm
        self.pwm = jumpto
        self.NewDuty(self.name, self.pwm)
        print ("     %s jumped to: %s" % (self.name, self.pwm))

        # this is the chunk of code that changes the displayed levels
        if self.name == "blower":
            global bpwmdisp
            bpwmdisp.set(str(blower.pwm))            
        elif self.name == "heater":
            global hpwmdisp
            hpwmdisp.set(str(heater.pwm))


# this function closes the program when you click the exit button
def close_window():
    heater.kill()
    blower.kill()
    GPIO.cleanup()
    exit()


# seperate function for closing the program using control-x keystroke
def close_windowkey(self):
    heater.kill()
    blower.kill()
    GPIO.cleanup()
    exit()


def organize(self):
    # NOW THAT LOGGING IS OVER - COMBINE THE INTERVALS INTO ONE intLIB
    global intLIB
    intLIB = []
    for i in range(len(heaterintervals)):
        time = heaterintervals[i][0]
        heat = heaterintervals[i][1]
        air = blowerintervals[i][1]
        alltogether = [time, heat, air]
        intLIB.append(alltogether)
    print("this is intLIB:")
    print (intLIB)
    

def gui():
    root = tkinter.Tk()
    root.wm_title("KALDI")
    # this is where the position of the opening windows can be set
    # as well as the size of the window
    # width x height + x_offset + y_offset:
    root.geometry("490x430+30+30")

    # THIS RUNS THE LOADED INTERVALS #  it is outside any class
    def intLIBloop():
        global intLIB
        global bpwmdisp
        global hpwmdisp
        for i in range(len(intLIB)):
            timesleep = int(intLIB[i][0])
            hpwm = int(intLIB[i][1])
            bpwm = int(intLIB[i][2])
            # this is the chunk of code that changes the displayed levels
            bpwmdisp.set(str(bpwm))            
            hpwmdisp.set(str(hpwm))

            # this code displays a declining interval number
            intervaldisplay.set(len(intLIB)-i)

            blowerpwm.ChangeDutyCycle(bpwm)
            heaterpwm.ChangeDutyCycle(hpwm)
            time.sleep(timesleep)
        intervaldisplay.set("FINISHED")
            
        print("END OF PROFILE")
        heaterpwm.ChangeDutyCycle(0)
        blowerpwm.ChangeDutyCycle(0)
        swpause()
        
        # this is the chunk of code that changes the displayed levels
        bpwmdisp.set('--')
        hpwmdisp.set('--')

    def looprunner():
        swreset()
        runner_thread = Thread(target=intLIBloop)
        runner_thread.start()

    """start the dialog box call for save as"""

    # this is the function/button that saves the profiles to a text file
    def saveit():
        global intLIB
        # open a file using asksaveasfile and storing it in "outfile"
        with tkinter.filedialog.asksaveasfile(mode='w') as outfile:
            writer = csv.writer(outfile)
            writer.writerows(intLIB)            
        outfile.close()
        print("Successfully printed everything to file!")         

    saveme = tkinter.Button(root, text="Save as to csv..", bg="#FFFFFF", fg="#000000",command=saveit)
    saveme.place(x=360, y=265, width=120, height=25)
    

    # this function opens a saved profile and loads it into blowerinterals/heaterintervals
    def loadit():
        global intLIB
        # open a file using askopenfile and storing it in "outfile" - LEFT OFF HERE
        with tkinter.filedialog.askopenfile(mode='r') as infile:
            reader = csv.reader(infile)
            rawimport = list(reader)
            intLIB = [list(map(float,rawimport)) for rawimport in rawimport]
        infile.close()
        print("intervals loaded: ")
        print(intLIB)
 
    loadme = tkinter.Button(root, text="Load Profile...", bg="#FFFFFF", fg="#000000",command=loadit)
    loadme.place(x=360, y=325, width=120, height=25)
    
    """END the dialog box stuff"""

    """import cool new stop watch app"""

    """STOPWATCH INNER WORKINGS"""
    def update_timeText():
        global state
        global timer
        global timestringdisp

        if (state):
            timer[2] += 1        
            if (timer[2] >= 100):
                timer[2] = 0
                timer[1] += 1
            if (timer[1] >= 60):
                timer[0] += 1
                timer[1] = 0
            timeString = pattern.format(timer[0], timer[1], timer[2])
            timeText.configure(text=timeString)
            timestringdisp = timeString
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

    # stop watch display label
    swDisp = tkinter.Label(text="STOPWATCH:", justify=LEFT, anchor=W)
    swDisp.place(x=10, y=360, width=120, height=25)
    
    # STOP WATCH DISPLAY
    global timeText
    timeText = tkinter.Label(root, text="00:00:00", bg="white", font=("Helvetica", 30), justify=LEFT, anchor=W)
    timeText.place(x=10, y=360, width=185, height=50)

    global timer
    timer = [0, 0, 0]
    global pattern
    pattern = '{0:02d}:{1:02d}:{2:02d}'
    """END STOP WATCH GUTS"""
    
    # stopwatch buttons
    
    # startButton = tkinter.Button(root, text='Start', command=swstart, bg="#00CC66")
    # startButton.place(x=185, y=360, height=50, width=40)

    # pauseButton = tkinter.Button(root, text='Stop', command=swpause, bg="#CC0000")
    # pauseButton.place(x=225, y=360, height=50, width=40)

    resetButton = tkinter.Button(root, text='Reset', command=swreset, bg="#FFFF00")
    resetButton.place(x=185, y=360, height=50, width=40)
    
    global state
    state = False
    """ END cool stop watch app"""

    # display labels for the PWM's
    # -----------------------------------------------------------------------------------
    global bpwmdisp
    bpwmdisp = StringVar()
    bpwmdisp.set("--")

    global hpwmdisp
    hpwmdisp = StringVar()
    hpwmdisp.set("--")

    global roasttime
    roasttime = StringVar()
    roasttime.set("00:00:00")

    global intervaldisplay
    intervaldisplay = StringVar()
    intervaldisplay.set('--')

    
    # display the current PWM of the heater and blower, also the total time for the roast
    l_roasttime = Label(root, text="ROAST TIME: ")
    l_roasttime.place(x=10, y=110, height=25)

    d_roasttime = Label(root, textvariable=roasttime, bg="beige")
    d_roasttime.place(x=90, y=110, height=20)

    # this displays the blowerlevel
    l_blowlevel = Label(root, text="BLOWER: ")
    l_blowlevel.place(x=10, y=135, height=25)

    d_blowlevel = Label(root, textvariable=bpwmdisp, bg="blue", fg="white")
    d_blowlevel.place(x=70, y=135, height=20)
    
    # this displays the heaterlevel
    l_heatlevel = Label(root, text="HEATER: ")
    l_heatlevel.place(x=10, y=160, height=25)
    
    d_heatlevel = Label(root, textvariable=hpwmdisp, bg="red", fg="white")
    d_heatlevel.place(x=70, y=160, height=20)

    # this displays number of intervals
    l_intervalnumber = Label(root, text="INTERVALS LEFT: ")
    l_intervalnumber.place(x=10, y=185, height=25)
    
    d_intervalnumber = Label(root, textvariable=intervaldisplay, fg="black")
    d_intervalnumber.place(x=120, y=187, height=20)
    # -----------------------------------------------------------------------------------
    

    # run the current interval
    def callback66():
        global intLIB
        print (intLIB)
        swstart()
        looprunner()             
    runme = tkinter.Button(root, text="Run This Profile", bg="#FFFFFF", fg="#000000",command=callback66)
    runme.place(x=360, y=355, width=120, height=25) 

    # nate's roaster label
    nr = Label(root, text="KALDI", fg="#B28F4F", font=("Helvetica", 75, "bold"))
    nr.place(width=490, height=95)
    
    # kill blower
    kill_blower = tkinter.Button(root, text="KILL", bg="#000000", fg="#00FFCC", command=lambda: blower.kill())
    kill_blower.place(x=310, y=90, width=40, height=25)

    # kill heater
    kill_heater = tkinter.Button(root, text="KILL", bg="#000000", fg="#FF3333", command=lambda: heater.kill())
    kill_heater.place(x=310, y=120, width=40, height=25)

    # reset interval library button
    def callback55():
        blowerlog.reset()
        heaterlog.reset()
        swreset()
        global primero
        primero = True
    reset = tkinter.Button(root, text="Reset Records", bg="#000000", fg="#00FFCC", command=callback55)
    reset.place(x=10, y=295, width=120, height=25)

    # print intervals button
    def callback1979():
        blowerlog.printit("heater")
        heaterlog.printit("blower")
    printit = tkinter.Button(root, text="Print Intervals", bg="#000000", fg="#00FFCC", command=callback1979)
    printit.place(x=10, y=265, width=120, height=25)

    # this kills heater and blower when control-k keystroke is hit
    def callback86(self):
        blower.kill()
        heater.kill()
        heaterlog.logit("heater", True)
        blowerlog.logit("blower", True)
        swpause()
        global timer
        global roasttime
        roasttime.set(timestringdisp)
        organize(self)

       
    root.bind('<Control-k>', callback86)
    
    # jumpto blower field
    jumptoair = tkinter.Entry(root, background="#00FFCC")
    jumptoair.place(x=185, y=90, width=120, height=25)
    jumptoair.focus_set()

    # jumpto heater field
    jumptoheat = tkinter.Entry(root, background="#FF3333")
    jumptoheat.place(x=185, y=120, width=120, height=25)
    jumptoheat.focus_set()    


    # jumpStart button for BOTH
    # we have to use a callback function b/c you can't fit all this in the "command=" field
    def callback4():
        global primero

        if primero == True:
            swstart()
            primero = False

        if jumptoheat.get() != "":
            heater.startjump(int(jumptoheat.get()))
            jumptoheat.delete(0, END)
            
        if jumptoair.get() != "":
            blower.startjump(int(jumptoair.get()))
            jumptoair.delete(0, END)

        blower.lognow()
        heater.lognow()

    def callback4key(self):
        global primero

        if primero == True:
            swstart()
            primero = False

        if jumptoheat.get() != "":
            heater.startjump(int(jumptoheat.get()))
            jumptoheat.delete(0, END)

        if jumptoair.get() != "":
            blower.startjump(int(jumptoair.get()))
            jumptoair.delete(0, END)

        blower.lognow()
        heater.lognow()
            
    jumpStart = tkinter.Button(root, text="jumpStart", bg="#0099FF", fg="#000000", command=callback4)
    jumpStart.place(x=185, y=170, width=120, height=25)
    # this binds the enter button to the the callback function which submits the jump info
    root.bind('<Control-Return>', callback4key)

    # Exit button
    quitme = tkinter.Button(root, text="EXIT", relief=RIDGE, bg="BLACK", fg="WHITE", command=close_window)
    quitme.place(x=360, y=295, width=120, height=25)
    # also quit everything when control-x keystroke is initiated
    root.bind('<Control-x>', close_windowkey)


    # END OF TKINTER WINDOW
    update_timeText()
    root.mainloop()

    
# start the logging module
blowerlog = recTime("blower")
heaterlog = recTime("heater")

# start two instances of modDuty
blower = modDuty("blower", 90, 10)
heater = modDuty("heater", 100, 10)

# set primero for the timer
global primero
primero = True

# start the GUI
gui = Thread(target=gui, args=())
gui.daemon = True
gui.start()










