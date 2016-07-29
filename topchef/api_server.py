"""
Very very very basic application
"""
import logging
from uuid import uuid1
from marshmallow_jsonschema import JSONSchema
from .config import config
from flask import Flask, jsonify, request, url_for
from datetime import datetime
from .models import Service, Job, UnableToFindItemError, FILE_MANAGER
from .decorators import check_json
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

app = Flask(__name__)
app.config.update(config.parameter_dict)

SESSION_FACTORY = sessionmaker(bind=config.database_engine)
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)


@app.route('/')
def hello_world():
    """
    Confirms that the API is working, and returns some metadata for the API

    **Example Response**

    .. sourcecode:: http

        HTTP/1.1 / GET
        Content-Type: application/json

        {
            "meta": {
                "author": "Michal Kononenko",
                "email": "michalkononenko@gmail.com",
                "source_repository":
                    "https://www.github.com/MichalKononenko/TopChef",
                "version": "0.1dev"
            }
        }

    :statuscode 200: The request was successful
    """
    return jsonify({
        'meta': {
            'source_repository': config.SOURCE_REPOSITORY,
            'version': config.VERSION,
            'author': config.AUTHOR,
            'email': config.AUTHOR_EMAIL
        }
    })


@app.route('/services', methods=["GET"])
def get_services():
    """
    Returns a list of services that have been registered with this API

    **Example Response**

    ..sourcecode:: http

        HTTP/1.1 /services GET
        Content-Type: application/json

        {
            "data": {
            }
        }
    """
    session = SESSION_FACTORY()
    service_list = session.query(Service).all()

    response = jsonify({
        'data': Service.ServiceSchema(many=True).dump(service_list).data,
        'meta': {
            "POST_schema":
                JSONSchema().dump(Service.DetailedServiceSchema()).data
        }
    })

    response.status_code = 200

    return response


@app.route('/services', methods=["POST"])
@check_json
def register_service():
    session = SESSION_FACTORY()

    new_service, errors = Service.DetailedServiceSchema().load(request.json)

    if errors:
        response = jsonify({
            'errors': {
                'message':'Invalid request, serializer produced errors.',
                'serializer_errors': errors
            }
        })
        response.status_code = 400
        return response

    session.add(new_service)

    try:
        session.commit()
    except IntegrityError as error:
        case_number = uuid1()
        LOG.error('case_number: %s; message: %s', case_number, error)
        session.rollback()
        response = jsonify({
            'errors': {
                'message': 'Integrity error thrown when trying to commit',
                'case_number': case_number
            }
        })
        response.status_code = 400
        return response

    response = jsonify(
        {'data': 'Service %s successfully registered' % new_service}
    )
    response.headers['Location'] = url_for(
        'get_service_data', service_id=new_service.id, _external=True
    )
    response.status_code = 201
    return response


@app.route('/services/<service_id>', methods=["GET"])
def get_service_data(service_id):
    session = SESSION_FACTORY()

    service = session.query(Service).filter_by(id=service_id).first()
    service.file_manager = FILE_MANAGER

    if service is None:
        response = jsonify({
            'errors': 'service with id=%s does not exist' % service_id
        })
        response.status_code = 404
        return response

    data, _ = service.DetailedServiceSchema().dump(service)

    return jsonify({'data': data})


@app.route('/services/<service_id>', methods=["PATCH"])
def heartbeat(service_id):
    session = SESSION_FACTORY()

    try:
        service = Service.from_session(session, service_id)
    except UnableToFindItemError:
        response = jsonify({
            'errors': 'The job with id %s does not exist'
        })
        response.status_code = 404
        return response

    service.heartbeat()

    session.add(service)
    session.commit()

    if not request.json:
        response = jsonify({
            'data': 'service %s checked in at %s' % (
                service.id, datetime.utcnow().isoformat()
            )
        })
        response.status_code = 200
        return response

    return jsonify({'meta': 'service %s has heartbeated at %s' % (
        service_id, datetime.now().isoformat()
    )})


@app.route('/services/<service_id>/jobs', methods=["GET"])
def get_jobs_for_service(service_id):
    session = SESSION_FACTORY()
    service = session.query(Service).filter_by(id=service_id).first()

    if not service:
        response = jsonify({
            'errors': 'A service with id %s was not found' % service_id
        })
        response.status_code = 404
        return response

    service.file_manager = FILE_MANAGER

    response = jsonify({
        'data': Job.JobSchema(many=True).dump(service.jobs).data
    })

    response.status_code = 200
    return response


@app.route('/services/<service_id>/jobs', methods=["POST"])
@check_json
def request_job(service_id):
    session = SESSION_FACTORY()
    service = session.query(Service).filter_by(id=service_id).first()

    if not service:
        response = jsonify({
            'errors': 'A service with id %s was not found' % service_id
        })
        response.status_code = 404
        return response

    service.file_manager = FILE_MANAGER

    job_data, errors = Job.JobSchema().load(request.json)

    if errors:
        response = jsonify({
            'errors': 'Schema loading produced errors %s' % errors
        })
        response.status_code = 400
        return response

    job = Job(service, job_data['parameters'])

    session.add(job)

    try:
        session.commit()
    except IntegrityError as error:
        case_number = uuid1()
        LOG.error('case_number: %s, message: %s' % case_number, error)
        session.rollback()

        response = jsonify({
            'errors': {
                'case_number': case_number,
                'message': 'Integrity error thrown when attempting commit'
            }
        })
        response.status_code = 400
        return response

    response = jsonify({
        'data': 'Job %s successfully created' % job.__repr__()
    })
    response.headers['Location'] = url_for(
        'get_job', job_id=job.id, _external=True
    )
    response.status_code = 201
    return response


@app.route('/jobs/<job_id>', methods=['GET'])
def get_job(job_id):
    session = SESSION_FACTORY()
    job = session.query(Job).filter_by(id=job_id).first()

    if not job:
        response = jsonify({
            'errors': 'A job with id %s was not found' % job_id
        })
        response.status_code = 404
        return response

    job.file_manager = FILE_MANAGER

    response = jsonify({'data': job.DetailedJobSchema().dump(job).data})
    response.status_code = 200
    return response


@app.route('/services/<service_id>/jobs/<job_id>', methods=["PUT"])
@check_json
def update_job_results(service_id, job_id):
    session = SESSION_FACTORY()

    service=session.query(Service).filter_by(id=service_id).first()
    if not service:
        response = jsonify({
            'errors': 'A service with id %s was not found' % service_id
        })
        response.status_code = 404
        return response

    job = session.query(Job).filter_by(id=job_id).first()
    if not job:
        response = jsonify({
            'errors': 'A job with id %s was not found' % job_id
        })
        response.status_code = 404
        return response

    new_job_data, errors = Job.DetailedJobSchema().load(request.json)

    job.update(new_job_data)

    session.add(job)

    try:
        session.commit()
    except IntegrityError as error:
        case_number = uuid1()
        LOG.error('case_number: %s, message: %s' % case_number, error)
        session.rollback()

        response = jsonify({
            'errors': {
                'case_number': case_number,
                'message': 'Integrity error thrown when attempting commit'
            }
        })
        response.status_code = 400
        return response
