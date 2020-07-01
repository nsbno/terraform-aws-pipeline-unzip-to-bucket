# terraform-aws-pipeline-unzip-to-bucket
A Terraform module that creates a Lambda function that downloads a ZIP file from one S3 bucket and unzips the contents to another S3 bucket, optionally deleting the previous contents of the target bucket.

The main use-case is deploy static frontend applications (SPA) from an artifact repository (S3), but it can be used for general unzipping purposes.

The Lambda can be set up allow invocations from multiple AWS accounts, in which case a Lambda alias `account-<account-id>` will be created for each of these accounts, which will then be used to make sure that the Lambda only can assume a role owned by the account that is equal to the account ID (i.e., the caller) in the alias.

## Lambda Inputs
The Lambda expects three different input parameters.

#### `account_id` (required)
The id of the account that owns the role `role_to_assume`.

#### `role_to_assume` (required)
The name of the role to assume. (Note: A policy should be attached to the the Lambda's execution role, exposed as an output in Terraform, that allows it to assume the role).

#### `s3_source_target_pairs` (required)
A list containing maps with information about which ZIP files to unzip to which buckets. Example:
```json
"s3_source_target_pairs": [
  {
    "s3_source_bucket": "my-source-bucket",
    "s3_source_key": "file.zip",
    "s3_source_version": "abcdef123456", 👈 Optional
    "s3_target_bucket": "my-target-bucket"
  }
]
```
