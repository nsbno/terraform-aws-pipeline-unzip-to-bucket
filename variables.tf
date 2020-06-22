variable "name_prefix" {
  description = "A prefix used for naming resources."
  type        = string
}

variable "tags" {
  description = "A map of tags (key-value pairs) passed to resources."
  type        = map(string)
  default     = {}
}

variable "lambda_timeout" {
  description = "The maximum number of seconds the Lambda is allowed to run"
  type        = number
  default     = 10
}

variable "trusted_accounts" {
  description = "A list of AWS account IDs that are allowed to invoke the function."
  type        = list(string)
  default     = []
}
