import pandas
from selenium.common import NoSuchElementException
from seleniumwire import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
import time
import requests
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import pandas as pd
from dotenv import load_dotenv
import os

login_url = "https://education.oneadvanced.com/"
timelog_url = "https://education.oneadvanced.com/cloud-education/timelog"
logs_post_url = "https://education.oneadvanced.com/api/cloud-education/v1/learner/bfc1ec38-cee0-4f60-85ec-a7d3cc278e55/activity-log"


def _wait_for_url_change(driver, original_url, timeout=30, poll_interval=0.5):
    end_time = time.time() + timeout
    while time.time() < end_time:
        if driver.current_url != original_url:
            return
        time.sleep(poll_interval)
    raise TimeoutError(f"URL did not change from {original_url} within {timeout}s — MFA may have failed or timed out")


def _wait_for_element(driver, by, selector, timeout=10, poll_interval=0.25):
    end_time = time.time() + timeout
    while True:
        try:
            element = driver.find_element(by, selector)
            if element:
                return element
        except NoSuchElementException:
            if time.time() > end_time:
                raise TimeoutError(f"Element '{selector}' not found within {timeout}s")
            time.sleep(poll_interval)


def prepare_browser() -> webdriver.Firefox:
    """Open browser and navigate to the OTP page, ready for MFA entry."""
    load_dotenv()
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--width=1920")
    options.add_argument("--height=1080")
    driver = webdriver.Firefox(service=Service("/snap/bin/geckodriver"), options=options)
    driver.get(login_url)

    username = os.getenv("username")
    OApasswd = os.getenv("OApasswd")

    _wait_for_element(driver, By.NAME, "emailOrUsername").send_keys(username + Keys.RETURN)
    _wait_for_element(driver, By.NAME, "username").send_keys(Keys.RETURN)
    _wait_for_element(driver, By.ID, "password").send_keys(OApasswd + Keys.RETURN)
    _wait_for_element(driver, By.ID, "otp")  # block until OTP page is loaded
    return driver


def check_non_empty_or_whitespace(row, row_index):
    for val in row:
        if pd.isna(val) or str(val).strip() == '':
            # row_index + 2: +1 for 1-based CSV rows, +1 for the header row
            raise ValueError(f"Row {row_index + 2} contains an empty string, whitespace, or NaN for a mandatory field. Mandatory fields are date, time-spent, start-time, and comments.")


def validate_date(date_value, row_index):
    try:
        pd.to_datetime(date_value, format='%Y/%m/%d')
    except ValueError:
        raise ValueError(f"Row {row_index + 2} contains an invalid date format. Expected: YYYY/MM/DD.")


def validate_time_spent(time_spent_value, row_index):
    try:
        pd.to_datetime(time_spent_value, format='%H:%M')
    except ValueError:
        raise ValueError(f"Row {row_index + 2} contains an invalid time-spent format. Expected: HH:MM.")


def validate_start_time(start_time_value, row_index):
    try:
        pd.to_datetime(start_time_value, format='%H:%M')
    except ValueError:
        raise ValueError(f"Row {row_index + 2} contains an invalid start-time format. Expected: HH:MM (24-hour).")


def login_and_submit_otjs(driver: webdriver.Firefox, mfa_code: str) -> dict:
    otj_df = pandas.read_csv("otjs.csv")
    unposted_otjs = otj_df[otj_df['posted'].isna()]
    unposted_otjs = unposted_otjs.drop('posted', axis=1, inplace=False)

    if unposted_otjs.empty:
        driver.quit()
        return {"posted": [], "failed": [], "nothing_to_post": True}

    for index, row in unposted_otjs.iterrows():
        check_non_empty_or_whitespace(row[:-1], index)
        validate_date(row['date'], index)
        validate_time_spent(row['time-spent'], index)
        validate_start_time(row['start-time'], index)

    post_data_template = {
        "learnerId": "bfc1ec38-cee0-4f60-85ec-a7d3cc278e55",
        "activityImpact": "",
        "unitId": "ef974f73-5d9d-447e-8652-379ba9535229",
        "activityDate": "2026-04-30",
        "activityTime": "T13:00:29",
        "activityType": 16,
        "hours": 2,
        "minutes": "00"
    }

    # Enter mfa code — send one char at a time so the OTP field's JS validators fire per keystroke
    input_field = _wait_for_element(driver, By.ID, "otp")
    input_field.click()
    for char in mfa_code:
        input_field.send_keys(char)
        time.sleep(0.05)
    otp_url = driver.current_url
    input_field.send_keys(Keys.RETURN)
    _wait_for_url_change(driver, otp_url)  # block until auth redirect completes

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])

    driver.quit()

    posted = []
    failed = []

    for index, row in unposted_otjs.iterrows():
        hours, minutes = row['time-spent'].split(':')
        post_data_template["activityDate"] = row['date'].replace('/', '-')
        post_data_template["activityImpact"] = row['comments']
        post_data_template["activityTime"] = f"T{row['start-time']}:00"
        post_data_template["hours"] = int(hours)
        post_data_template["minutes"] = minutes
        response = session.post(logs_post_url, json=post_data_template)
        if response.status_code == 200:
            otj_df.at[index, 'posted'] = True
            otj_df.to_csv('otjs.csv', index=False)
            posted.append(index + 2)
        else:
            failed.append({"row": index + 2, "status_code": response.status_code, "response": response.text})

    return {"posted": posted, "failed": failed, "nothing_to_post": False}
