terraform {
  required_providers {
    tencentcloud = {
      source  = "tencentcloudstack/tencentcloud"
      version = "~> 1.81"
    }
  }
}

provider "tencentcloud" {
  region = var.region
}

# Security group — allow SSH + HTTP
resource "tencentcloud_security_group" "clawdramas" {
  name        = "clawdramas-sg"
  description = "ClawDramas server security group"
}

resource "tencentcloud_security_group_lite_rule" "clawdramas" {
  security_group_id = tencentcloud_security_group.clawdramas.id

  ingress = [
    "ACCEPT#0.0.0.0/0#80#TCP",
    "ACCEPT#${var.admin_ip}/32#22#TCP",
  ]

  egress = [
    "ACCEPT#0.0.0.0/0#ALL#ALL",
  ]
}

# CVM instance
resource "tencentcloud_instance" "clawdramas" {
  instance_name     = "clawdramas"
  availability_zone = var.availability_zone
  image_id          = var.image_id
  instance_type     = var.instance_type

  system_disk_type = "CLOUD_BSSD"
  system_disk_size = 50

  internet_max_bandwidth_out = 10
  allocate_public_ip         = true

  orderly_security_groups = [tencentcloud_security_group.clawdramas.id]

  key_ids = var.key_ids

  tags = {
    project = "clawdramas"
  }
}
