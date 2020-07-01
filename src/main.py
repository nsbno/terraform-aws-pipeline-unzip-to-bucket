#!/usr/bin/env python3.7
#
# Copyright (C) 2020 Vy
#
# Distributed under terms of the MIT license.

"""
Downloads a .zip-file from one S3 bucket and unzips the contents to another.
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
    extension = filename.rsplit(".")[-1].lower()
    content_type = content_types.get(extension, "application/octet-stream")
    return content_type


def assume_role(account_id, account_role):
    sts_client = boto3.client("sts")
    role_arn = f"arn:aws:iam::{account_id}:role/{account_role}"
    assuming_role = True
    retry_wait_in_seconds = 5
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


def unzip_and_upload_to_target_bucket(
    zip_file,
    target_bucket,
    target_prefix="",
    delete_old_objects=False,
    boto_kwargs={},
):
    """Unzips a ZIP file and uploads it to an S3 bucket, optionally deleting old objects upon successful upload.

    Args:
        zip_file: A bytes buffer containing the ZIP file.
        target_bucket: The name of the S3 bucket to upload the contents of the
            ZIP file to.
        target_prefix: An optional prefix to use when uploading files to the target S3 bucket.
        delete_old_objects: Whether to delete all objects in the target bucket
            that were not part of the ZIP file.
        boto_kwargs: An optional dictionary containing arguments that will
            be passed into boto3 (e.g., credentials).
    """

    s3 = boto3.client("s3", **boto_kwargs)

    with zipfile.ZipFile(zip_file, "r") as z:
        zip_files = z.namelist()
        upload_keys = [
            f"{target_prefix and target_prefix + '/'}{f}" for f in zip_files
        ]
        logger.debug("Found zip files '%s'", zip_files)
        logger.info(
            "Uploading zip files to '%s'",
            f"{target_bucket}{target_prefix and target_prefix + '/'}",
        )
        responses = [
            s3.put_object(
                Bucket=target_bucket,
                Key=upload_keys[i],
                Body=z.open(f),
                ContentType=get_content_type(f),
            )
            for i, f in enumerate(zip_files)
        ]
        logger.debug("Received upload responses from S3: '%s'", responses)
        if delete_old_objects:
            response = s3.list_objects_v2(
                Bucket=target_bucket, Prefix=target_prefix
            )
            objects = response["Contents"]
            while response["IsTruncated"]:
                response = s3.list_objects_v2(
                    Bucket=target_bucket,
                    ContinuationToken=response["NextContinuationToken"],
                    Prefix=target_prefix,
                )
                objects = objects + response["Contents"]
            old_files = list(
                filter(
                    lambda key: key not in upload_keys,
                    map(lambda file: file["Key"], objects),
                ),
            )
            logger.debug(
                "Deleting files from target bucket that were not in zip file: '%s'",
                old_files,
            )
            if len(old_files):
                s3.delete_objects(
                    Bucket=target_bucket,
                    Delete={"Objects": [{"Key": key} for key in old_files]},
                )


def get_alias_from_arn(arn):
    """Return the alias (if any) used for invoking the function"""
    alias = arn.split(":")[-1] if len(arn.split(":")) == 8 else None
    if alias:
        logger.debug("Lambda was invoked using alias '%s'", alias)
    else:
        logger.debug("Lambda was not invoked by an alias")
    return alias


def lambda_handler(event, context):
    logger.debug("Lambda triggered with input data '%s'", json.dumps(event))

    region = os.environ["AWS_REGION"]
    account_id = event["account_id"]
    role_to_assume = event["role_to_assume"]
    s3_source_target_pairs = event["s3_source_target_pairs"]

    lambda_alias = get_alias_from_arn(context.invoked_function_arn)
    if lambda_alias:
        invoked_by = lambda_alias.split("account-")[-1]
        logger.debug("Lambda was invoked by account with id '%s'", invoked_by)
        if invoked_by and invoked_by != account_id:
            logger.error(
                "Lambda was invoked by account '%s', but wants to assume a role in account '%s'",
                invoked_by,
                account_id,
            )
            raise ValueError()

    for pair in s3_source_target_pairs:
        target_bucket = pair["s3_target_bucket"]
        retries = 0
        while True:
            try:
                credentials = assume_role(account_id, role_to_assume)
                boto_kwargs = {
                    "aws_access_key_id": credentials["AccessKeyId"],
                    "aws_secret_access_key": credentials["SecretAccessKey"],
                    "aws_session_token": credentials["SessionToken"],
                    "region_name": region,
                }
                s3 = boto3.client("s3", **boto_kwargs)
                s3.head_bucket(Bucket=target_bucket)
                break
            except botocore.exceptions.ClientError:
                logger.warning("Failed to access bucket '%s'", target_bucket)
                if retries > 5:
                    logger.exception(
                        "Exceeded number of retries for bucket access"
                    )
                    raise
                logger.warning("Sleeping for 5 seconds, and then retrying")
                time.sleep(5)
                retries += 1

    for pair in s3_source_target_pairs:
        s3_source_bucket = pair["s3_source_bucket"]
        s3_source_key = pair["s3_source_key"]
        s3_source_version = pair.get("s3_source_version", None)
        s3_target_bucket = pair["s3_target_bucket"]

        zip_file = get_file_from_s3(
            s3_source_bucket, s3_source_key, s3_source_version
        )
        unzip_and_upload_to_target_bucket(
            zip_file,
            s3_target_bucket,
            delete_old_objects=True,
            boto_kwargs=boto_kwargs,
        )

    return
