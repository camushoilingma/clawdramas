variable "region" {
  description = "Tencent Cloud region"
  type        = string
  default     = "ap-tokyo"
}

variable "availability_zone" {
  description = "Availability zone"
  type        = string
  default     = "ap-tokyo-2"
}

variable "instance_type" {
  description = "CVM instance type"
  type        = string
  default     = "SA2.MEDIUM4" # 2 vCPU, 4GB RAM
}

variable "image_id" {
  description = "Ubuntu 22.04 image ID (region-specific)"
  type        = string
  default     = "img-487zeit5" # Ubuntu 22.04 LTS ap-tokyo
}

variable "key_ids" {
  description = "SSH key pair IDs"
  type        = list(string)
}

variable "admin_ip" {
  description = "Admin IP address for SSH access (without /32)"
  type        = string
}
