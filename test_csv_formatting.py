import unittest
import pandas as pd


def row_to_post_data(row, template):
    hours, minutes = row['time-spent'].split(':')
    data = template.copy()
    data["activityDate"] = row['date'].replace('/', '-')
    data["activityImpact"] = row['comments']
    data["activityTime"] = f"T{row['start-time']}:00"
    data["hours"] = int(hours)
    data["minutes"] = minutes
    return data


TEMPLATE = {
    "learnerId": "bfc1ec38-cee0-4f60-85ec-a7d3cc278e55",
    "unitId": "ef974f73-5d9d-447e-8652-379ba9535229",
    "activityDate": None,
    "activityTime": None,
    "activityType": 16,
    "hours": None,
    "minutes": None,
    "activityImpact": None,
}


class TestCsvFormatting(unittest.TestCase):

    def setUp(self):
        self.row = pd.Series({
            'date': '2026/01/01',
            'time-spent': '1:00',
            'start-time': '11:00',
            'comments': 'Did some reading.',
        })
        self.result = row_to_post_data(self.row, TEMPLATE)

    def test_activity_date_format(self):
        self.assertRegex(self.result['activityDate'], r'^\d{4}-\d{2}-\d{2}$')

    def test_activity_date_value(self):
        self.assertEqual(self.result['activityDate'], '2026-01-01')

    def test_activity_time_format(self):
        self.assertRegex(self.result['activityTime'], r'^T\d{2}:\d{2}:\d{2}$')

    def test_activity_time_value(self):
        self.assertEqual(self.result['activityTime'], 'T11:00:00')

    def test_hours_is_int(self):
        self.assertIsInstance(self.result['hours'], int)

    def test_hours_value(self):
        self.assertEqual(self.result['hours'], 1)

    def test_minutes_is_string(self):
        self.assertIsInstance(self.result['minutes'], str)

    def test_minutes_value(self):
        self.assertEqual(self.result['minutes'], '00')

    def test_activity_impact_value(self):
        self.assertEqual(self.result['activityImpact'], 'Did some reading.')

    def test_static_fields_unchanged(self):
        self.assertEqual(self.result['learnerId'], TEMPLATE['learnerId'])
        self.assertEqual(self.result['unitId'], TEMPLATE['unitId'])
        self.assertEqual(self.result['activityType'], TEMPLATE['activityType'])


if __name__ == '__main__':
    unittest.main()
