import pyotp

def start_live_mfa_display():
    totp = pyotp.TOTP("JB2FI52YGFBXI3CCGN3HQ52QO5GVSZJWJ52HIV2IK5IEETDR")

    def update_code():
        current_code = totp.now()
        print(current_code)
    update_code()    
start_live_mfa_display()