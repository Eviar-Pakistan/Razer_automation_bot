import pyotp

def start_live_mfa_display():
    totp = pyotp.TOTP("G5RGOT2UN4ZUSMZWJJTECTLGIFBDAZSNIEZTQ2DUJIYWUUT2")

    def update_code():
        current_code = totp.now()
        print(current_code)
    update_code()    
start_live_mfa_display()