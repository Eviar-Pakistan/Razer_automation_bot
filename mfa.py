import pyotp

def start_live_mfa_display():
    totp = pyotp.TOTP("GU2XSSTRJI2E26CUM5GGMQZVKN2E2ODPGMZHGYRRNNREGWKC")

    def update_code():
        current_code = totp.now()
        print(current_code)
    update_code()    
start_live_mfa_display()