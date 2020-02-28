output "function_name" {
  description = "The name of the Lambda function."
  value       = aws_lambda_function.pipeline_unzip_to_bucket.id
}

output "lambda_exec_role_id" {
  description = "The name of the execution role given to the lambda."
  value       = aws_iam_role.lambda_exec.id
}
