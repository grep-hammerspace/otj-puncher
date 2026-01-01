import datetime
import json
from pickle import GLOBAL, TRUE

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

# Get the password from the environment variable
password = os.getenv('MY_PASSWORD')



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

# Evaluate the start time column
post_data_template = {
  "DateCreated": "26/09/2025 00:00:00",
  "CreatedBy": "bfc1ec38-cee0-4f60-85ec-a7d3cc278e55",
  "ParentUserId": "bfc1ec38-cee0-4f60-85ec-a7d3cc278e55",
  "OriginId": "Manual",
  "TrainingScheduleId": "",
  "SessionCourseId": "",
  "SessionLinkHasFeedback": "False",
  "IsDfeFundingRuleDateToBeValidated": "True",
  "ActivityImpactRequired": "True",
  "hdnDfeFundingRuleDate": "01/08/2023",
  "Date": "dummy",
  "ParentActivityId": "19",
  "UnitId": "{ef974f73-5d9d-447e-8652-379ba9535229}",
  "ParentModuleId": "", #
  "TimeWithAssessorId": "501133f8-46bf-4565-b6b1-82c4d038f437",
  "OnTheJob": "1",
  "TimeValue": "dummy",
  "ActivityStartTimeValue": "dummy",
  "Comments": "dummy",
  "IsAssessorApproved": "false",
  "ApprovedAssessorId": ""
}

# Endpoint to submit GET and POST requests.
form_url = "https://www.smartassessor.co.uk/ETimeSheet/Form"

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
driver.get(form_url)

username = os.getenv("username")
password = os.getenv("password")
OApasswd = os.getenv("OApasswd")

# SmartAssesor Page
wait_for_element(By.NAME, "Username").send_keys(username)
wait_for_element(By.NAME, "Password").send_keys(password + Keys.RETURN)

# OneAdvanced Page
wait_for_element(By.ID, "username").send_keys(username + Keys.RETURN)
wait_for_element(By.ID, "password").send_keys(OApasswd)
wait_for_element(By.ID, "kc-login").click()

# Locate the input field and the button
input_field = wait_for_element(By.ID, "otp")
button = wait_for_element(By.ID, "kc-login")

# TODO: Add a check here to see if we are actually waiting for the auth code, if we arent we can skip to filling the form

# Polling loop
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

# Define the session headers that we can use to send the POST request
session_headers = None
for request in driver.requests:
    print(request)
    if request.headers.get("Referer") == form_url:
        session_headers = request.headers


def format_date(date_string):
    sections = date_string.split("/")
    date = datetime.datetime(int(sections[0]), int(sections[1]), int(sections[2]))
    print (f" date format {str(date)}")
    return str(date)

if session_headers == None:
    print("No usable session headers found, unable to log OTJS, exiting")
    exit(1)
else:
    print (f"found the correct session header:  {session_headers}")
    print( " Posting unposted otjs")

    for index,row in unposted_otjs.iterrows():
        post_data_template["Date"] = row['date']
        post_data_template["Comments"] = row['comments']
        post_data_template["ActivityStartTimeValue"] = row['start-time']
        post_data_template["DateCreated"] = f"{datetime.datetime.today().strftime("%d/%m/%Y")} 00:00:00"
        post_data_template["TimeValue"] = row['time-spent']
        response = requests.post(form_url, headers=session_headers, data=post_data_template)
        if response.status_code == 200:
            # Persist information about successful logs, so we dont send the same thing twice.
            print("Status Code:", response.status_code)
            print("Response Text:", response.text)
            otj_df.at[index, 'posted'] = True
            otj_df.to_csv('otjs.csv', index=False)
        else:
            print(f"------------------ Error Logging Otj In Row {index + 2} -----------------------------------")
            print("Status Code:", response.status_code)
            print("Response Text:", response.text)




