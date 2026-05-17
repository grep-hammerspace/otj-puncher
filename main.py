import datetime
import json
import pandas
from selenium.common import NoSuchElementException
from seleniumwire import webdriver
from selenium.webdriver.firefox.service import Service
import time
import requests
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
import pandas as pd
from dotenv import load_dotenv
import os

otj_df = pandas.read_csv("otjs.csv")
unposted_otjs = otj_df[otj_df['posted'].isna()]

# Drop the posted column because we dont need it while doing the checks.
unposted_otjs =  unposted_otjs.drop('posted', axis=1, inplace=False)


# Load environment variables from .env file
load_dotenv()


def check_non_empty_or_whitespace(row, row_index):
    for val in row:
        if pd.isna(val) or str(val).strip() == '':
            # We do row_index + 2 bc we lose 1 starting from instead of 0 in the csv, and another 1 when converting to a pd
            raise ValueError(f"Row {row_index + 2} contains an empty string, whitespace, or NaN for a mandatory field. Mandatory fields are date, time-spent,start-time, and comments. Ensure mandatory fields are filled correctly then re run")

# Function to validate date format (YYYY/MM/DD)
def validate_date(date_value, row_index):
    try:
        pd.to_datetime(date_value, format='%Y/%m/%d')
    except ValueError:
        raise ValueError(f"Row {row_index + 2} contains an invalid date format. Expected format: YYYY/MM/DD. Ensure the correct format then re-run")

# Function to validate time-spent format (HH:MM)
def validate_time_spent(time_spent_value, row_index):
    try:
        pd.to_datetime(time_spent_value, format='%H:%M')
    except ValueError:
        raise ValueError(f"Row {row_index + 2} contains an invalid time-spent format. Expected format: HH:MM. Ensure the correct format then re-run")

# Function to validate start-time format (HH:MM) in 24-hour format
def validate_start_time(start_time_value, row_index):
    try:
        pd.to_datetime(start_time_value, format='%H:%M')
    except ValueError:
        raise ValueError(f"Row {row_index + 2} contains an invalid start-time format. Expected format: HH:MM (24-hour format). Ensure the correct format then re-run")

# Check no funny business in the csv.
for index,row in unposted_otjs.iterrows():
    check_non_empty_or_whitespace(row[:-1], index)
    validate_date(row['date'], index)
    validate_time_spent(row['time-spent'], index)
    validate_start_time(row['start-time'], index)

print("All checks passed successfully. The data is valid.")

# Format of request body that is sent to log OTJs.
post_data_template = {
    "learnerId": "bfc1ec38-cee0-4f60-85ec-a7d3cc278e55",
    "activityImpact": "As part of a supplimentary curriculum at GS, I did some coding problems around Data Structures And Algorithms, here is a github repo with soime of the work i did https://github.com/grep-hammerspace/supplimetary_curriculum/tree/main/module1. \nI did the exercises in goland because I am trying to learn it as a new programming language",
    "unitId": "ef974f73-5d9d-447e-8652-379ba9535229",
    "activityDate": "2026-04-30",
    "activityTime": "T13:00:29",
    "activityType": 16,
    "hours": 2,
    "minutes": "00"
}

# Endpoint to submit GET and POST requests.
login_url = "https://education.oneadvanced.com/"
timelog_url = "https://education.oneadvanced.com/cloud-education/timelog"
logs_post_url = "https://education.oneadvanced.com/api/cloud-education/v1/learner/bfc1ec38-cee0-4f60-85ec-a7d3cc278e55/activity-log"

driver = webdriver.Firefox(service=Service("/snap/bin/geckodriver"))


# try to write a method that will wait until a field is available
def wait_for_element(by, selector, target_count=10, timeout=10, poll_interval=0.25):
    end_time = time.time() + timeout
    while True:
        try:
            element = driver.find_element(by, selector)
            if element:
                return element
        except NoSuchElementException:
            if time.time() > end_time:
                raise TimeoutError(
                    f"Expected at least {target_count} elements, found nothing"
                )
            time.sleep(poll_interval)


# Open target URL
driver.get(login_url)

username = os.getenv("username")
password = os.getenv("password")
OApasswd = os.getenv("OApasswd")

# OneAdvancedLoginPage
wait_for_element(By.NAME, "emailOrUsername").send_keys(username + Keys.RETURN)
wait_for_element(By.NAME, "username").send_keys(Keys.RETURN)
wait_for_element(By.ID, "password").send_keys(OApasswd + Keys.RETURN)


# Locate the input field and the button
input_field = wait_for_element(By.ID, "otp")
button = wait_for_element(By.ID, "kc-login")

# TODO: Add a check here to see if we are actually waiting for the auth code, if we arent we can skip to filling the form

# Crude spin lock type thing to continuously poll for the user filling in the MFA code.
while True:
    # Check if input field has text
    field_filled = len(input_field.get_attribute("value").strip()) == 6

    # Check if button is enabled (some sites disable button until input is filled)
    button_enabled = button.is_enabled()

    # TODO : add some logic here that will allow for retrying incorrect passwords
    if field_filled and button_enabled:
        button.click()
        break

    # sleep so we dont cook the CPU
    time.sleep(0.2)

# At this point we are logged in, so we navigate to the timelog page
driver.get(timelog_url)

# Grab site cookies and format them for re-use when actually logging the data via POST calls
session = requests.Session()
for cookie in driver.get_cookies():
    session.cookies.set(cookie['name'], cookie['value'])

print("Posting unposted otjs")

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
    else:
        print(f"------------------ Error Logging Otj In Row {index + 2} -----------------------------------")
        print("Status Code:", response.status_code)
        print("Response Text:", response.text)




