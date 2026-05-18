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
    driver = webdriver.Firefox(service=Service("/snap/bin/geckodriver"), options=options)
    driver.get(login_url)

    username = os.getenv("username")
    OApasswd = os.getenv("OApasswd")

    _wait_for_element(driver, By.NAME, "emailOrUsername").send_keys(username + Keys.RETURN)
    _wait_for_element(driver, By.NAME, "username").send_keys(Keys.RETURN)
    _wait_for_element(driver, By.ID, "password").send_keys(OApasswd + Keys.RETURN)
    _wait_for_element(driver, By.ID, "otp")  # block until OTP page is loaded
    return driver


def login_and_submit_otjs(driver: webdriver.Firefox, mfa_code: str) -> str:
    otj_df = pandas.read_csv("otjs.csv")
    unposted_otjs = otj_df[otj_df['posted'].isna()]
    unposted_otjs = unposted_otjs.drop('posted', axis=1, inplace=False)

    def check_non_empty_or_whitespace(row, row_index):
        for val in row:
            if pd.isna(val) or str(val).strip() == '':
                # We do row_index + 2 bc we lose 1 starting from instead of 0 in the csv, and another 1 when converting to a pd
                raise ValueError(f"Row {row_index + 2} contains an empty string, whitespace, or NaN for a mandatory field. Mandatory fields are date, time-spent,start-time, and comments. Ensure mandatory fields are filled correctly then re run")

    def validate_date(date_value, row_index):
        try:
            pd.to_datetime(date_value, format='%Y/%m/%d')
        except ValueError:
            raise ValueError(f"Row {row_index + 2} contains an invalid date format. Expected format: YYYY/MM/DD. Ensure the correct format then re-run")

    def validate_time_spent(time_spent_value, row_index):
        try:
            pd.to_datetime(time_spent_value, format='%H:%M')
        except ValueError:
            raise ValueError(f"Row {row_index + 2} contains an invalid time-spent format. Expected format: HH:MM. Ensure the correct format then re-run")

    def validate_start_time(start_time_value, row_index):
        try:
            pd.to_datetime(start_time_value, format='%H:%M')
        except ValueError:
            raise ValueError(f"Row {row_index + 2} contains an invalid start-time format. Expected format: HH:MM (24-hour format). Ensure the correct format then re-run")

    for index, row in unposted_otjs.iterrows():
        check_non_empty_or_whitespace(row[:-1], index)
        validate_date(row['date'], index)
        validate_time_spent(row['time-spent'], index)
        validate_start_time(row['start-time'], index)

    print("All checks passed successfully. The data is valid.")

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
    input_field.send_keys(Keys.RETURN)

    driver.get(timelog_url)

    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])

    driver.quit()

    print("Posting unposted otjs")
    posted = []

    for index, row in unposted_otjs.iterrows():
        hours, minutes = row['time-spent'].split(':')
        post_data_template["activityDate"] = row['date'].replace('/', '-')
        post_data_template["activityImpact"] = row['comments']
        post_data_template["activityTime"] = f"T{row['start-time']}:00"
        post_data_template["hours"] = int(hours)
        post_data_template["minutes"] = minutes
        response = session.post(logs_post_url, json=post_data_template)
        if response.status_code == 200:
            print("Status Code:", response.status_code)
            print("Response Text:", response.text)
            otj_df.at[index, 'posted'] = True
            otj_df.to_csv('otjs.csv', index=False)
            posted.append(index)
        else:
            print(f"------------------ Error Logging Otj In Row {index + 2} -----------------------------------")
            print("Status Code:", response.status_code)
            print("Response Text:", response.text)

    return f"Posted {len(posted)} OTJ(s): rows {[i + 2 for i in posted]}"
