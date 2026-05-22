import oci
import os
import time
import logging
from datetime import datetime

config = {
    "user":        os.environ["OCI_USER_OCID"],
    "tenancy":     os.environ["OCI_TENANCY_OCID"],
    "fingerprint": os.environ["OCI_FINGERPRINT"],
    "region":      os.environ["OCI_REGION"],
    "key_content": os.environ["OCI_PRIVATE_KEY"],
}

COMPARTMENT_ID      = os.environ["OCI_COMPARTMENT_ID"]
SUBNET_ID           = os.environ["OCI_SUBNET_ID"]
IMAGE_ID            = os.environ["OCI_IMAGE_ID"]
SSH_PUBLIC_KEY      = os.environ["OCI_SSH_PUBLIC_KEY"]
AVAILABILITY_DOMAIN = os.environ["OCI_AVAILABILITY_DOMAIN"]

RETRY_INTERVAL_SEC = 60
MAX_ATTEMPTS       = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def try_create(compute):
    try:
        resp = compute.launch_instance(
            oci.core.models.LaunchInstanceDetails(
                compartment_id=COMPARTMENT_ID,
                availability_domain=AVAILABILITY_DOMAIN,
                display_name=f"a1-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
                shape="VM.Standard.A1.Flex",
                shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
                    ocpus=4,
                    memory_in_gbs=24,
                ),
                source_details=oci.core.models.InstanceSourceViaImageDetails(
                    image_id=IMAGE_ID,
                    source_type="image",
                ),
                create_vnic_details=oci.core.models.CreateVnicDetails(
                    subnet_id=SUBNET_ID,
                    assign_public_ip=True,
                ),
                metadata={"ssh_authorized_keys": SSH_PUBLIC_KEY},
            )
        )
        return resp.data.id

    except oci.exceptions.ServiceError as e:
        if "Out of host capacity" in (e.message or ""):
            log.warning("용량 부족 — 재시도 예정")
        elif e.status == 429:
            log.warning("Rate limit — 재시도 예정")
        else:
            log.error(f"API 오류 {e.status}: {e.message}")
        return None


def main():
    compute = oci.core.ComputeClient(config)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        log.info(f"시도 #{attempt}/{MAX_ATTEMPTS}")

        instance_id = try_create(compute)
        if instance_id:
            log.info(f"생성 요청 성공 — OCID: {instance_id}")
            log.info("RUNNING 상태 대기 중...")
            oci.wait_until(
                compute,
                compute.get_instance(instance_id),
                "lifecycle_state", "RUNNING",
                max_wait_seconds=600,
            )
            log.info("✅ 인스턴스 생성 완료!")
            exit(0)

        if attempt < MAX_ATTEMPTS:
            log.info(f"{RETRY_INTERVAL_SEC}초 대기...")
            time.sleep(RETRY_INTERVAL_SEC)

    log.warning("이번 실행에서 생성 실패 — 다음 스케줄에 재시도됩니다")
    exit(1)


if __name__ == "__main__":
    main()
