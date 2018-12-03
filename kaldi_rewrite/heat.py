class heater():
    def __init__(self):
        self.pwm = 0
    def newduty(self, pwm):
        self.pwm = pwm
        print(f'new HEATER duty cycle: {self.pwm}')
    def ppwm(self):
        print(f'HEATER: {self.pwm}')