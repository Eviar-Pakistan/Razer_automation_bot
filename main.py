import tkinter as tk
from tkinter import ttk, messagebox
from playwright.sync_api import sync_playwright
import pyotp
import threading
import time
import json
import os
import sys
import queue
import asyncio
import subprocess
import random
import requests
if not os.path.exists(os.path.expanduser("~/.ms-playwright")):
    print("Installing Playwright browsers...")
    subprocess.run(["playwright", "install"], shell=True)

CONFIG_FILE = "accounts.json"
MFA_FILE = "mfa_secrets.txt"
VOUCHER_FILE = "vouchers.txt"
otp_code = None
live_otp_code = None
log_text_widget = None
input_frame = None
entry_link = entry_email = entry_password = None
global_email = global_password = None
global_link = None
product_vars = {}
page = None
click_queue = queue.Queue()
user_selector = None
email_label = None
password_label = None
backup_codes = []
global_gold = None
global_silver = None

def is_internet_available(timeout=5):
    try:
        requests.get("https://www.google.com", timeout=timeout)
        return True
    except requests.ConnectionError:
        return False

def log_to_textbox(text):
    if log_text_widget:
        log_text_widget.configure(state='normal')
        log_text_widget.insert(tk.END, text + '\n')
        log_text_widget.see(tk.END)
        log_text_widget.configure(state='disabled')

class TextRedirector:
    def write(self, s): log_to_textbox(s.strip())
    def flush(self): pass

def save_credentials(email, password):
    data = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
    data[email] = password
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved credentials for {email}")

def load_credentials():
    if not os.path.exists(CONFIG_FILE):
        return {}
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def deletePreviousAuthenticator():
    if not is_internet_available():
        print("⚠️ No internet connection. Please check your network.")
        return    
    page.locator("button.btn.arrowed", has_text="Choose a different method").click()
    page.get_by_role("button", name="Backup Codes").click()
    code_to_use = random.choice(backup_codes)
    otp_inputs = page.locator(".input-group-otp-2 input.input-otp")
    for i, digit in enumerate(code_to_use):
        otp_inputs.nth(i).fill(digit)
    print("Backup code entered.")
    time.sleep(2)
    print("Deleting the previous authenticator")
    page.wait_for_selector(".tfa-item")
    page.click(".tfa-item")
    page.locator("#btn-2-step-auth-delete").click()
    page.locator("#btn-popover-delete").click()
    return

   

def collectProducts(key):
    log_text_widget.after(0, lambda: start_live_mfa_display(key))
    if not is_internet_available():
        print("⚠️ No internet connection. Please check your network.")
        return    
    page.goto(global_link)
    print(f"Navigating to: {global_link}")
    print("Collecting Products from the page....")
    time.sleep(2)
    results = []
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    safe_email = global_email.replace("@", "_at_").replace(".", "_")
    filename = f"vouchers_{safe_email}_{timestamp}.txt"
    product_labels = page.query_selector_all(".selection-tile")
    page.click(".selection-tile-promos__details")
    for tile in product_labels:
        try:
            name_elem = tile.query_selector(".selection-tile__text")
            if not name_elem:
                continue
            name = name_elem.inner_text().strip()
            label_elem = tile.query_selector("label")
            if label_elem:
                label_elem.click()
            else:
                tile.click()
            time.sleep(1.5)
            price_elem = (page.query_selector(".media-row__flex-item-right span") or page.query_selector(".price-value") or tile.query_selector(".price"))
            price = price_elem.inner_text().strip() if price_elem else "N/A"
            results.append({"product": name, "price": price})
        except Exception as e:
            print(f"Error: {e}")
    log_text_widget.after(0, lambda: display_products(results))
    def wait_for_product_clicks():
        while True:
            if not is_internet_available():
                print("⚠️ No internet connection. Please check your network.")
                return
            try:
                product_name, quantity = click_queue.get(timeout=0.5)
                try:
                    index = int(str(e).split("index")[1].strip())
                except:
                    index = 0
                handle_product_click(product_name, quantity, retry=True, start_index=index, filename=filename)
            except queue.Empty:
                continue
    wait_for_product_clicks()
    return
def get_last_secret_key(email=None):
    if not email:
        email = global_email

    try:
        with open(MFA_FILE, "r") as f:
            lines = f.readlines()

        matched_lines = [line.strip() for line in lines if line.strip().startswith(f"{email}:")]
        if not matched_lines:
            print(f"No MFA key found for {email}")
            return None

        last_line = matched_lines[-1]

        if "(mfa setup by me)" not in last_line:
            print("⚠️ MFA is setup with another authenticator.")
            deletePreviousAuthenticator()
            setupAuthenticatorAndCollectProducts()
            return None

        key_part = last_line.split(":", 1)[1]
        key = key_part.split("(mfa setup by me)")[0].strip()
        return key

    except Exception as e:
        print(f"Error reading MFA file for {email}: {e}")
        return None


def save_secret_key(email, secret_key):
    with open(MFA_FILE, "a") as f:
        f.write(f"{email}: {secret_key} (mfa setup by me)\n")

def start_live_mfa_display(secret_key):
    totp = pyotp.TOTP(secret_key)
    def update_code():
        global live_otp_code
        current_code = totp.now()
        live_otp_code = current_code
        seconds_remaining = totp.interval - (int(time.time()) % totp.interval)
        code_label.config(text=f"Code: {current_code} | Expires in: {seconds_remaining}s")
        code_label.after(1000, update_code)
    update_code()

def setup_inputs():
    global entry_link, entry_email, entry_password, user_selector, email_label, password_label
    credentials = load_credentials()
    input_frame.pack(pady=10)

    for widget in input_frame.winfo_children():
        widget.destroy()

    tk.Label(input_frame, text="Link").pack()
    entry_link = tk.Entry(input_frame, width=50)
    entry_link.pack()

    saved_emails = list(credentials.keys())
    saved_emails.append("Add New User")

    user_selector = ttk.Combobox(input_frame, values=saved_emails, state="readonly")
    user_selector.set(saved_emails[0])
    user_selector.pack(pady=5)

    entry_email = tk.Entry(input_frame, width=50)
    entry_password = tk.Entry(input_frame, width=50, show="*")
    email_label = tk.Label(input_frame, text="Email")
    password_label = tk.Label(input_frame, text="Password")

    def toggle_fields(event=None):
        selected = user_selector.get()
        if selected == "Add New User":
            email_label.pack()
            entry_email.pack()
            password_label.pack()
            entry_password.pack()
        else:
            email_label.pack_forget()
            entry_email.pack_forget()
            password_label.pack_forget()
            entry_password.pack_forget()

    user_selector.bind("<<ComboboxSelected>>", toggle_fields)
    toggle_fields()
    tk.Label(input_frame, text="Backup Codes (optional, space-separated)").pack()
    entry_backup = tk.Entry(input_frame, width=50)
    entry_backup.pack()

    def on_submit():
        global global_email, global_password, global_link , backup_codes
        global_link = entry_link.get().strip()
        backup_input = entry_backup.get().strip()
        if backup_input:
            backup_codes = backup_input.split()
            print(f"🔐 Backup codes saved: {backup_codes}")
        selected = user_selector.get()

        if selected == "Add New User":
            global_email = entry_email.get().strip()
            global_password = entry_password.get().strip()
            if not (global_link and global_email and global_password):
                messagebox.showerror("Error", "All fields are required.")
                return
            save_credentials(global_email, global_password)
        else:
            global_email = selected
            global_password = credentials[selected]
            if not global_link:
                messagebox.showerror("Error", "Link is required.")
                return

        input_frame.pack_forget()
        messagebox.showinfo("Success", "Setup completed. You can now Run Scan.")

    tk.Button(input_frame, text="Save & Continue", command=on_submit).pack(pady=5)



from datetime import datetime

written_products = set()

def save_voucher(email, product, code, serial, filename, url=None):
    global written_products
    try:
        with open(filename, "a") as f:
            if product not in written_products:
                f.write(f"{product}\n")
                written_products.add(product)
            f.write(f"Code: {code} | Serial: {serial}\n")

        print(f"📄 Voucher saved to {filename}")
    except Exception as e:
        print(f"❌ Failed to save voucher: {e}")



import time


from datetime import datetime
import time

def handle_product_click(product_name, quantity, retry=False, start_index=0, filename=None):
    global page, live_otp_code, global_email, global_link
    if not is_internet_available():
        print("⚠️ No internet connection. Please check your network.")
        return      
    try:
        quantity = int(quantity)
        print(f"Selected product: {product_name} | Quantity: {quantity}")
        page.wait_for_selector(".selection-tile__text")
        page.click(f"text={product_name}")
        page.click(".selection-tile-promos__details")

        if not filename:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_email = global_email.replace("@", "_at_").replace(".", "_")
            filename = f"vouchers_{safe_email}_{timestamp}.txt"


        for i in range(start_index, quantity):
            print(f"\n➡️ Purchase {i + 1} of {quantity}")

            try:
                if not is_internet_available():
                    print("⚠️ No internet connection. Please check your network.")
                    return  
                button_locator = page.locator('[data-cs-override-id^="purchase-webshop-"][data-cs-override-id$="checkout-btn"]').first
                button_locator.wait_for()
                button_text = button_locator.text_content().strip()

                if button_text == "RELOAD TO CHECKOUT":
                    print("❗ You have insufficient funds!")
                    return
                elif button_text == "Checkout":
                    with page.expect_navigation():
                        button_locator.click()
                else:
                    print("❓ Unexpected button text!")
                    return

                transaction_url = page.url
                max_retries = 10
                retry_delay = 2

                pin_code_text = ""
                serial_number_text = ""

    
                for attempt in range(max_retries):

                    try:
                        if not is_internet_available():
                            print("⚠️ No internet connection. Please check your network.")
                            return  
                        page.wait_for_selector(".pin-code", timeout=10000)
                        pin_code_element = page.locator(".pin-code")
                        serial_element = page.locator(".pin-serial-number")

                        pin_code_text = pin_code_element.text_content().strip()
                        serial_number_text = serial_element.text_content().strip()

                        if pin_code_text and serial_number_text:
                            break
                        else:
                            print(f"🔁 Retry {attempt + 1}/{max_retries} - Pin or Serial not found yet.")
                            time.sleep(retry_delay)
                    except Exception as wait_error:
                        print(f"⚠️Waiting for strong connection: {wait_error}")
                        page.goto(global_link)
                        try:
                            index = int(str(e).split("index")[1].strip())
                        except:
                            index = 0
                        handle_product_click(product_name, quantity, retry=True, start_index=index, filename=filename)
                        time.sleep(retry_delay)

                if not pin_code_text or not serial_number_text:
                    raise Exception("Pin or Serial Number is empty")
                
        

                voucher_code = pin_code_text
                serial_number = serial_number_text.replace("S/N:", "").strip()

                save_voucher(global_email, product_name, voucher_code, serial_number, filename=filename, url=transaction_url)
                print(f"💾 Voucher saved: {voucher_code} | Serial: {serial_number}")

            except Exception as e_inner:
                if not is_internet_available():
                    print("⚠️ No internet connection. Please check your network.")
                    return      
                print(f"❌ Transaction failed at item {i + 1}. Reason: {e_inner}")
                page.goto(global_link)
                raise Exception(f"Resuming needed from index {i}")
            if i < quantity - 1:
                page.goto(global_link)
                page.wait_for_selector(".selection-tile__text")
                page.click(f"text={product_name}")
                page.click(".selection-tile-promos__details")

        page.goto(global_link)

    except Exception as e:
        print(f"❌ Error during product purchase: {e}")
        if not is_internet_available():
            print("⚠️ No internet connection. Please check your network.")
            return          
        unlock_profile()
        print("🔁 Retrying purchase after unlocking profile...")
        page.goto(global_link)
        try:
            index = int(str(e).split("index")[1].strip())
        except:
            index = 0
        handle_product_click(product_name, quantity, retry=True, start_index=index, filename=filename)





def handle_product_click_with_page(product_name, quantity):
    click_queue.put((product_name, quantity))

def display_products(results):
    for widget in product_display_frame.winfo_children():
        widget.destroy()
    canvas = tk.Canvas(product_display_frame, height=400)
    scrollbar = ttk.Scrollbar(product_display_frame, orient="vertical", command=canvas.yview)
    scroll_frame = ttk.Frame(canvas)
    scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
    scrollbar.pack(side="right", fill="y")
    product_vars.clear()
    for item in results:
        frame = ttk.Frame(scroll_frame)
        frame.pack(fill="x", pady=4, padx=4)
        qty_var = tk.StringVar(value="1")
        def make_handler(product_name, qty_var):
            return lambda: handle_product_click_with_page(product_name, qty_var.get())
        product_button = ttk.Button(
            frame,
            text=item['product'],
            width=40,
            command=make_handler(item['product'], qty_var)
        )
        product_button.pack(side="left", padx=(0, 10))
        price_label = ttk.Label(frame, text=item['price'], foreground="green", width=10)
        price_label.pack(side="left")
        qty_dropdown = ttk.Combobox(
            frame,
            textvariable=qty_var,
            values=[str(i) for i in range(1, 11)],
            width=3
        )
        qty_dropdown.pack(side="left", padx=10)
        product_vars[item['product']] = {"qty": qty_var, "price": item['price']}



def unlock_profile():
    try:
        page.goto("https://razerid.razer.com/account/security/setup")
        page.wait_for_load_state("networkidle")

        try:
            status_element = page.query_selector("span.info.align-left.text-ellipsis.text-green")
            if status_element:
                status_text = status_element.inner_text().strip()
                if "Enabled" in status_text:
                    print("✅ MFA is enabled. Redirecting...")
                    page.goto(global_link)
                    return
        except Exception as status_err:
            print(f"⚠️ Unable to detect MFA status text: {status_err}")

        try:
            description = page.text_content(".modal-description.mb-15.text-gray").strip().lower()
        except:
            description = ""

        if "enter the code generated by your authenticator" in description:
            print("🔐 MFA prompt detected.")
            key = get_last_secret_key()
            start_live_mfa_display(key)

            if key:
                try:
                    page.wait_for_selector(".input-group-otp input", timeout=5000)
                    final_inputs = page.query_selector_all(".input-group-otp input")
                    if len(final_inputs) != 6:
                        print("⚠️ Final OTP input fields missing.")
                        return

                    for i, digit in enumerate(live_otp_code):
                        final_inputs[i].fill(digit)

                    print("✅ MFA code entered.")
                    time.sleep(2)
                    page.goto(global_link)
                    return
                except Exception as otp_err:
                    print(f"⚠️ Error filling OTP: {otp_err}")
        
        print("⚠️ MFA status unknown. Redirecting to main link.")
        page.goto(global_link)

    except Exception as e:
        print(f"❌ Failed to unlock profile or check MFA status: {e}")



def setupAuthenticatorAndCollectProducts():
    if not is_internet_available():
        print("⚠️ No internet connection. Please check your network.")
        return    
    print("Selecting Authenticator App...")
    page.wait_for_selector(".tfa-item")
    page.click(".tfa-item")
    page.wait_for_selector(".secret-key", state="attached")
    secret_key = page.text_content(".secret-key").strip()
    print(f"Secret Key: {secret_key}")
    save_secret_key(global_email, secret_key)
    page.click("#btn-next")
    print("Clicked 'Next'")
    page.wait_for_selector(".input-group-otp input")
    totp = pyotp.TOTP(secret_key)
    final_code = totp.now()
    final_inputs = page.query_selector_all(".input-group-otp input")
    if len(final_inputs) != 6:
        print("Final OTP fields missing.")
        return
    for i, digit in enumerate(final_code): final_inputs[i].fill(digit)
    print("Final OTP entered.")
    time.sleep(2)
    page.click("#btn-next")
    print("Clicked final 'Next'")
    try:
        if not is_internet_available():
            print("⚠️ No internet connection. Please check your network.")
            return        
        page.wait_for_selector("#btn-finish")
        page.click("#btn-finish")
        print("MFA Setup Completed!")
        log_text_widget.after(0, lambda: start_live_mfa_display(secret_key))
        page.goto(global_link)
        print(f"Navigating to: {global_link}")
        print("Collecting Products from the page....")
        time.sleep(2)
        results = []
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe_email = global_email.replace("@", "_at_").replace(".", "_")
        filename = f"vouchers_{safe_email}_{timestamp}.txt"
        product_labels = page.query_selector_all(".selection-tile")
        page.click(".selection-tile-promos__details")
        for tile in product_labels:
            try:
                name_elem = tile.query_selector(".selection-tile__text")
                if not name_elem:
                    continue
                name = name_elem.inner_text().strip()
                label_elem = tile.query_selector("label")
                if label_elem:
                    label_elem.click()
                else:
                    tile.click()
                time.sleep(1.5)
                price_elem = (page.query_selector(".media-row__flex-item-right span") or page.query_selector(".price-value") or tile.query_selector(".price"))
                price = price_elem.inner_text().strip() if price_elem else "N/A"
                results.append({"product": name, "price": price})
            except Exception as e:
                print(f"Error: {e}")
        log_text_widget.after(0, lambda: display_products(results))
        def wait_for_product_clicks():
            while True:
                try:
                    product_name, quantity = click_queue.get(timeout=0.5)
                    try:
                        index = int(str(e).split("index")[1].strip())
                    except:
                        index = 0
                    handle_product_click(product_name, quantity, retry=True, start_index=index, filename=filename)
                except queue.Empty:
                    continue
        wait_for_product_clicks()
    except:
        print("Finish button not found or already clicked.")
    print("\nLive MFA Codes (refreshing every 30 seconds):") 

def stop_bot():
    print("🛑 Stopping bot and closing application...")
    try:
        page.context.browser.close()
    except:
        pass
    # sys.exit()



def start_main_ui():
    global log_text_widget, input_frame, gold_label, silver_label, product_display_frame,code_label

    root = tk.Tk()
    root.title("Razer Automation")
    root.geometry("750x750")
    root.resizable(True, False)
    log_text_widget = tk.Text(root, height=12, state='disabled', bg="#1e1e1e", fg="#3cff00")
    log_text_widget.pack(padx=10, pady=(10, 5), fill=tk.X)

    code_label = tk.Label(root, text="", font=("Courier", 14), fg="#ff0000")
    code_label.pack(pady=(0, 10))

    input_frame = tk.Frame(root)
    input_frame.pack()
    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=5)
    tk.Button(btn_frame, text="Setup", command=setup_inputs, width=20).pack(side=tk.LEFT, padx=10)
    tk.Button(btn_frame, text="Run Scan", command=lambda: threading.Thread(target=automate, daemon=True).start(), width=20).pack(side=tk.RIGHT, padx=10)
    tk.Button(btn_frame, text="Stop Razer Bot", command=stop_bot, width=20, fg="red").pack(side=tk.LEFT, padx=10)
    balance_frame = tk.Frame(root)
    balance_frame.pack(pady=5)
    gold_label = tk.Label(balance_frame, text="Gold: --", font=("Helvetica", 12), fg="#f1c40f")
    gold_label.pack(side=tk.LEFT, padx=20)
    silver_label = tk.Label(balance_frame, text="Silver: --", font=("Helvetica", 12), fg="#bdc3c7")
    silver_label.pack(side=tk.LEFT, padx=20)
    product_display_frame = tk.Frame(root)
    product_display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    sys.stdout = TextRedirector()
    root.mainloop()

def automate():
    global global_email, global_password, global_link, page

    if not is_internet_available():
        print("⚠️ No internet connection. Please check your network.")
        return

    credentials = load_credentials()
    if not global_email or not global_password:
        if credentials:
            global_email, global_password = next(iter(credentials.items()))
            print(f"Using saved credentials for {global_email}")
        else:
            print("No credentials found. Please run setup first.")
            return
    if not global_link:
        print("No link provided. Please set it up.")
        return
    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    page = browser.new_page()
    print("Launching browser...")
    if not is_internet_available():
        print("⚠️ No internet connection. Please check your network.")
        return
    page.goto("https://razerid.razer.com/")
    page.fill("#input-login-email", global_email)
    page.fill("#input-login-password", global_password)
    page.click("#btn-log-in")
    print("Submitted login form.")
    print("Login successful.")
    page.wait_for_url("**/dashboard")
    try:
        if not is_internet_available():
            print("⚠️ No internet connection. Please check your network.")
            return
        page.wait_for_selector("div.gold .info-balance")
        global_gold = page.locator("div.gold .info-balance").text_content().strip()
        global_silver = page.locator("div.silver .info-balance").text_content().strip()
        gold_label.config(text=f"Gold: {global_gold}")
        silver_label.config(text=f"Silver: {global_silver}")
    except Exception as e:
        print(f"Error retrieving balances: {e}")
    try:
        page.click(".cky-btn.cky-btn-accept")
    except:
        pass
    if not is_internet_available():
        print("⚠️ No internet connection. Please check your network.")
        return    
    page.goto("https://razerid.razer.com/account/security/setup")
    try:
        if not is_internet_available():
            print("⚠️ No internet connection. Please check your network.")
            return        
        description = page.text_content(".modal-description.mb-15.text-gray").strip().lower()
        if "enter the code generated by your authenticator" in description:
            print("MFA is already set up.")
            key = get_last_secret_key()
            start_live_mfa_display(key)
            if key:
                page.wait_for_selector(".input-group-otp input")
                final_inputs = page.query_selector_all(".input-group-otp input")
                if len(final_inputs) != 6:
                    print("Final OTP fields missing.")
                    return
                for i, digit in enumerate(live_otp_code): final_inputs[i].fill(digit)
                print("MFA code entered.")
                time.sleep(2)
                collectProducts(key=key)
            
                
        else:
            if not is_internet_available():
                print("⚠️ No internet connection. Please check your network.")
                return            
            print("Waiting for OTP modal...")
            page.wait_for_selector(".input-group-otp input")
            print("OTP modal detected!")
            def prompt_for_otp():
                def on_submit():
                    global otp_code
                    otp_code = entry.get().strip()
                    if len(otp_code) != 6 or not otp_code.isdigit():
                        messagebox.showerror("Invalid OTP", "Please enter a valid 6-digit code.")
                        return
                    otp_frame.pack_forget()
                otp_frame = tk.Frame(log_text_widget.master)
                tk.Label(otp_frame, text="Enter 6-digit OTP:").pack(pady=5)
                entry = tk.Entry(otp_frame, justify='center', font=("Helvetica", 14))
                entry.pack()
                tk.Button(otp_frame, text="Continue", command=on_submit).pack(pady=5)
                otp_frame.pack(pady=10)
            log_text_widget.after(0, prompt_for_otp)
            while not otp_code or len(otp_code) != 6 or not otp_code.isdigit():
                time.sleep(1)
            otp_inputs = page.query_selector_all(".input-group-otp input")
            if len(otp_inputs) != 6:
                print("OTP input fields not found.")
                return
            for i, digit in enumerate(otp_code): otp_inputs[i].fill(digit)
            print("OTP entered.")
            setupAuthenticatorAndCollectProducts()
    except Exception as e:
        print(f"Failed to check existing MFA setup: {e}")
        

start_main_ui()

