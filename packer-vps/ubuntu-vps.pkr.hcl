packer {
  required_plugins {
    openstack = {
      version = ">= 1.0.0"
      source  = "github.com/hashicorp/openstack"
    }
  }
}

source "openstack" "ubuntu_vps" {
  cloud           = "my-openstack"
  tenant_id	  = "Project_A"
  image_name      = "ubuntu-22.04-monitoring-v1"
  source_image    = "57d47e9f-ff9a-42c9-ad77-2e268989fe9e"
  flavor          = "m1.small"
  network_discovery_cidrs = ["10.0.0.0/24"]
  floating_ip_network = "ext_net"

  ssh_username    = "ubuntu"
  volume_size = 10
}

build {
  sources = ["source.openstack.ubuntu_vps"]

  # 스크립트 실행으로 환경 구성
  provisioner "shell" {
    script = "scripts/setup-exporter.sh"
  }
}
