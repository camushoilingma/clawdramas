output "public_ip" {
  description = "Public IP of the ClawDramas server"
  value       = tencentcloud_instance.clawdramas.public_ip
}

output "instance_id" {
  description = "CVM instance ID"
  value       = tencentcloud_instance.clawdramas.id
}
