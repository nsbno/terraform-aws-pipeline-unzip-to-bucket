#!/usr/bin/env python3.7
#
# Copyright (C) 2020 Erlend Ekern <dev@ekern.me>
#
# Distributed under terms of the MIT license.

"""
Downloads a .zip-file from an S3 bucket in account A,
and unzips the contents to an S3 bucket in account B
"""

import boto3
import botocore
import zipfile
import io
import json
import os
import time
import logging
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_content_type(filename):
    """Finds the content type of a typical website file based on its extension.

    Args:
        filename: A string representing the filename.

    Returns:
        The content type of the file if the file is a typical
        website file, or a default content type if not.
    """

    content_types = {
        "bmp": "image/bmp",
        "css": "text/css",
        "gif": "image/gif",
        "htm": "text/html",
        "html": "text/html",
        "ico": "image/x-icon",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "js": "application/x-javascript",
        "json": "application/json",
        "png": "image/png",
        "svg": "image/svg+xml",
    }
    extension = filename.rsplit(".")[-1]
    content_type = content_types.get(extension, "application/octet-stream")
    return content_type


def assume_role(account_id, account_role):
    sts_client = boto3.client("sts")
    role_arn = f"arn:aws:iam::{account_id}:role/{account_role}"
    assuming_role = True
    retry_wait_in_seconds = 15
    while assuming_role:
        try:
            logger.info("Trying to assume role with arn '%s'", role_arn)
            assumedRoleObject = sts_client.assume_role(
                RoleArn=role_arn, RoleSessionName="NewAccountRole"
            )
            assuming_role = False
        except botocore.exceptions.ClientError:
            assuming_role = True
            logger.exception("Failed to assume role with arn '%s'", role_arn)
            logger.info(
                "Retrying role assumption for role with arn '%s' in %ss",
                role_arn,
                retry_wait_in_seconds,
            )
            time.sleep(retry_wait_in_seconds)
    logger.info("Successfully assumed role with arn '%s'", role_arn)
    return assumedRoleObject["Credentials"]


def get_file_from_s3(s3_bucket, s3_key, s3_version_id=None):
    s3 = boto3.client("s3")
    try:
        if s3_version_id is None:
            response = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        else:
            response = s3.get_object(
                Bucket=s3_bucket, Key=s3_key, VersionId=s3_version_id
            )
    except Exception:
        logger.exception(
            "Failed to download file '%s/%s' from S3", s3_bucket, s3_key
        )
        raise
    file = io.BytesIO(response["Body"].read())
    return file


def find_bucket_by_prefix(prefix, boto_kwargs):
    """Finds one S3 bucket with a name that matches a prefix.

    Args:
        prefix: The name prefix to use when finding the S3 bucket.
        boto_kwargs: A dictionary containing arguments that will
            be passed into boto3 (e.g., credentials).

    Returns:
        The name of the S3 bucket that matches the given prefix.

    Raises:
        Exception: Did not find exactly 1 matching buckets.
    """

    s3 = boto3.client("s3", **boto_kwargs)
    response = s3.list_buckets(**boto_kwargs)
    buckets = list(
        filter(
            lambda name: name.startswith(prefix),
            map(lambda bucket: bucket["Name"], response["Buckets"]),
        )
    )
    if len(buckets) != 1:
        logger.error(
            "Expected to find 1 bucket matching the prefix '%s', but found '%s': '%s'",
            prefix,
            len(buckets),
            buckets,
        )
        raise Exception()

    return buckets[0]


def unzip_and_upload_to_target_bucket(zip_file, target_bucket, boto_kwargs):
    """Unzips a ZIP file and uploads it to an S3 bucket.

    Args:
        zip_file: A bytes buffer containing the ZIP file.
        target_bucket: The name of the S3 bucket to upload the contents of the
            ZIP file to.
        boto_kwargs: A dictionary containing arguments that will
            be passed into boto3 (e.g., credentials).
    """

    s3 = boto3.client("s3", **boto_kwargs)
    with zipfile.ZipFile(zip_file, "r") as z:
        contents = z.namelist()
        logger.debug("Found zip contents '%s'", contents)
        logger.debug("Uploading zip contents to S3 bucket '%s'", target_bucket)
        responses = [
            s3.put_object(
                Bucket=target_bucket,
                Key=f,
                Body=z.open(f),
                ContentType=get_content_type(f),
            )
            for f in contents
        ]
        logger.debug("Received upload responses from S3: '%s'", responses)
        bucket_contents = s3.list_objects_v2(Bucket=target_bucket)["Contents"]
        old_files = list(
            filter(
                lambda key: key not in contents,
                map(lambda file: file["Key"], bucket_contents),
            ),
        )
        logger.debug(
            "Found existing files in target bucket that were not in zip file: '%s'",
            old_files,
        )
        # logger.debug("Deleting old files from S3: '%s'", old_files)
        # bucket.delete_objects(
        #    Delete={"Objects": [{"Key": key} for key in old_files]}
        # )


def lambda_handler(event, context):
    logger.debug("Lambda triggered with input data '%s'", json.dumps(event))

    region = os.environ["AWS_REGION"]
    account_id = event["account_id"]
    cross_account_role = event["cross_account_role"]
    s3_source_target_pairs = event["s3_source_target_pairs"]

    credentials = assume_role(account_id, cross_account_role)
    boto_kwargs = {
        "aws_access_key_id": credentials["AccessKeyId"],
        "aws_secret_access_key": credentials["SecretAccessKey"],
        "aws_session_token": credentials["SessionToken"],
        "region_name": region,
    }

    for pair in s3_source_target_pairs:
        s3_source_bucket = pair["s3_source_bucket"]
        s3_source_key = pair["s3_source_key"]
        s3_target_bucket = pair["s3_target_bucket"]

        zip_file = get_file_from_s3(s3_source_bucket, s3_source_key)
        unzip_and_upload_to_target_bucket(
            zip_file, s3_target_bucket, boto_kwargs
        )

    return
