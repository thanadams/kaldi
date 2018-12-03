class controller():
    def __init__(self, name, pwm):
        self.name = name
        self.pwm = pwm

    def newduty(self, newpwm):
        self.pwm = newpwm
        print(f'new {self.name} duty cycle: {self.pwm}')


b = controller('blower', 0)
h = controller('heater', 0)

print("Enter blower duty desired:")
duty = int(input('>'))
b.newduty(duty)

print("Enter heater duty desired:")
duty = int(input('>'))
h.newduty(duty)