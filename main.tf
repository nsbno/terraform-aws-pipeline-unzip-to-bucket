# ------------------------------------------------------------------------------
# Resources
# ------------------------------------------------------------------------------
data "aws_caller_identity" "current-account" {}
data "aws_region" "current" {}

locals {
  current_account_id = data.aws_caller_identity.current-account.account_id
  current_region     = data.aws_region.current.name
}

data "archive_file" "lambda_src" {
  type        = "zip"
  source_file = "${path.module}/src/main.py"
  output_path = "${path.module}/src/bundle.zip"
}

resource "aws_lambda_function" "pipeline_unzip_to_bucket" {
  function_name    = "${var.name_prefix}-pipeline-unzip-to-bucket"
  handler          = "main.lambda_handler"
  role             = aws_iam_role.lambda_exec.arn
  runtime          = "python3.7"
  filename         = data.archive_file.lambda_src.output_path
  source_code_hash = filebase64sha256(data.archive_file.lambda_src.output_path)
  timeout          = 10
  tags             = var.tags
}

resource "aws_iam_role" "lambda_exec" {
  name               = "${var.name_prefix}-pipeline-unzip-to-bucket"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "logs_to_lambda" {
  policy = data.aws_iam_policy_document.logs_for_lambda.json
  role   = aws_iam_role.lambda_exec.id
}
