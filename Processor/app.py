import connexion
import requests
import yaml
import logging
import logging.config
from apscheduler.schedulers.background import BackgroundScheduler
import os
import json
from datetime import datetime, timedelta, timezone
from statistics import mean
from connexion import NoContent


with open("app_conf.yml", "r") as f:
	app_config = yaml.safe_load(f.read())

with open("log_conf.yml", "r") as f:
	log_config = yaml.safe_load(f.read())
	logging.config.dictConfig(log_config)

logger = logging.getLogger('basicLogger')

def get_json_data():
	if os.path.isfile(app_config['datastore']['filename']):
		with open(app_config['datastore']['filename'], 'r') as f:
			return json.load(f)
	else:
		return {
			"num_enrolled_students": 0,
       		"min_enrolled_student_gpa": 4.0,
      		"avg_enrolled_student_gpa": 0,
      	 	"num_drop_out_students": 0,
      		"max_drop_out_student_gpa": 0.0,
      		"avg_drop_out_student_gpa": 0,
			"last_updated": datetime.strftime(datetime.now() - timedelta(seconds=5), '%Y-%m-%dT:%H:%M:%S')
		}


def populate_stats():
	"""Periodically update stats"""
	logger.info("Periodic processing has started")
	
	json_data = get_json_data()

	logger.debug(json_data)

	start_timestamp = json_data['last_updated']
	current_date = datetime.strftime(datetime.now(), '%Y-%m-%dT:%H:%M:%S')

	header = {"Content-Type": "application/json"}
	params = {"start_timestamp": start_timestamp, "end_timestamp": current_date}
	try:
		enroll_response = requests.get(f"{app_config['eventstore']['url']}/enroll", params=params, headers=header)
		drop_out_response = requests.get(f"{app_config['eventstore']['url']}/drop-out", params=params, headers=header)
	except Exception as e:
		logger.exception(e)

	logger.info(f"Received {len(enroll_response.json())} enroll events")
	logger.info(f"Received {len(drop_out_response.json())} drop-out events")
	
	if enroll_response.status_code != 200:
		logger.error("Did not receive a 200 response code from enroll endpoint")
		return
	if drop_out_response.status_code != 200:
		logger.error("Did not receive a 200 response code from drop-out endpoint")
		return
	
	# logger.debug(enroll_response.json())
	
	enroll_gpa = [event["highschool_gpa"] for event in enroll_response.json()]
	drop_out_gpa = [event["program_gpa"] for event in drop_out_response.json()]

	enroll_gpa += [json_data["min_enrolled_student_gpa"]]
	drop_out_gpa += [json_data["max_drop_out_student_gpa"]]
	
	json_data["num_enrolled_students"] += len(enroll_response.json())
	json_data["min_enrolled_student_gpa"] = min(enroll_gpa)
	json_data["avg_enrolled_student_gpa"] = mean(enroll_gpa)
	json_data["num_drop_out_students"] += len(drop_out_response.json())
	json_data["max_drop_out_student_gpa"] = max(drop_out_gpa)
	json_data["avg_drop_out_student_gpa"] = mean(drop_out_gpa)
	json_data["last_updated"] = current_date

	logger.debug(json_data)

	with open(app_config['datastore']['filename'], 'w') as f:
		json.dump(json_data, f, indent=4)


def get_stats():
	logger.info("Request for statistics has been received")

	if not os.path.isfile(app_config['datastore']['filename']):
		logger.error("Statistics do not exist")
		return
	
	statistics = {}
	try:
		with open(app_config['datastore']['filename']) as f:
			statistics = json.load(f)
			logger.info(statistics)
	except FileNotFoundError:
		logger.error("No statistics found")
		return NoContent, 404


	logger.debug(f"Statistics: {statistics}")
	logger.info("Request has been completed")

	return statistics, 200


def init_scheduler():
	sched = BackgroundScheduler(daemon=True)
	sched.add_job(populate_stats,
				  'interval',
				  seconds=app_config['scheduler']['period_sec'])
	sched.start()


# def enroll_student(body):
# 	body["trace_id"] = str(uuid.uuid4())

# 	logger.info(f"Received event enroll request with a trace id of {body["trace_id"]}")

# 	header = {"Content-Type": "application/json"}
	
# 	response = requests.post(app_config["enroll"]["url"], json=body, headers=header)
	
# 	logger.info(f"Returned event enroll response (id: {body["trace_id"]}) with status {response.status_code}")

# 	return NoContent, response.status_code


# def withdraw_student(body):
# 	body["trace_id"] = str(uuid.uuid4())

# 	logger.info(f"Received event drop-out request with a trace id of {body["trace_id"]}")
	
# 	header = {"Content-Type": "application/json"}
# 	response = requests.post(app_config["drop-out"]["url"], json=body, headers=header)

# 	logger.info(f"Returned event drop-out response (id: {body["trace_id"]}) with status {response.status_code}")
	
# 	return NoContent, response.status_code


app = connexion.FlaskApp(__name__, specification_dir='')
app.add_api("openapi.yaml", strict_validation=True, validate_responses=True)

if __name__ == "__main__":
	init_scheduler()
	app.run(port=8100)