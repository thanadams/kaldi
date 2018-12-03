class blower():
    def __init__(self, pwm):
        self.pwm = pwm
        print(pwm)

    def newduty(self, newpwm):
        self.pwm = newpwm
        print(f'new blower duty cycle: {self.pwm}')