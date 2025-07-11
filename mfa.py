import pyotp

def start_live_mfa_display():
    totp = pyotp.TOTP("LJ4TONLXHF3XOSDRNNSHIWKMJF4EOYSGMZSVOVRQNZDTA3RU")

    def update_code():
        current_code = totp.now()
        print(current_code)
    update_code()    
start_live_mfa_display()