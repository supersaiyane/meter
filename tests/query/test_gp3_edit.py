"""gp2 to gp3 as an edit, on real Terraform text. TASK-P15-005, FEAT-093, OPEN-43.

The one block that declares the volume is changed: `type` to gp3, and `iops` and `throughput`
where the volume needs more than gp3 includes, with the file kept as `terraform fmt` keeps it.
Everything the edit cannot read for certain is refused with the reason, and strings, comments and
heredocs never count as code.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from finops_core.domain.waste import WasteClass
from finops_core.ports.pull_requests import RepositoryFile
from finops_query.gp3_edit import Edited, Gp3Figures, author_gp3, edit_volume
from finops_query.remediation import NotAuthored, RecommendationFacts

ADDRESS = "aws_ebs_volume.data"
INCLUDED = Gp3Figures(iops=3000, mibps=125)
MORE = Gp3Figures(iops=6000, mibps=250)

STORAGE = """\
# The data volume. "type" below is gp2 { not a brace }
resource "aws_ebs_volume" "data" {
  availability_zone = "eu-west-1a"
  size              = 500
  type              = "gp2" # set in 2021

  tags = {
    Name = "data"
  }
}

resource "aws_iam_policy" "reader" {
  policy = <<EOF
{ "Statement": [ { "Effect": "Allow" } ] }
EOF
}
"""


def edited(text: str, figures: Gp3Figures = INCLUDED, address: str = ADDRESS) -> Edited:
    found = edit_volume((RepositoryFile("storage/main.tf", text),), address, figures)
    assert isinstance(found, Edited), found
    return found


def refused(files: tuple[RepositoryFile, ...], figures: Gp3Figures, address: str) -> str:
    found = edit_volume(files, address, figures)
    assert isinstance(found, NotAuthored), found
    return found.reason


def test_the_type_is_changed_in_place_and_its_comment_kept() -> None:
    found = edited(STORAGE)
    assert found.path == "storage/main.tf"
    assert found.content == STORAGE.replace('"gp2" # set', '"gp3" # set')
    assert found.said == ('`type` set to "gp3"',)


def test_iops_and_throughput_are_added_where_gp3_must_give_more_aligned_as_fmt_would() -> None:
    found = edited(STORAGE, MORE)
    assert (
        '  type              = "gp3" # set in 2021\n'
        "  iops              = 6000\n"
        "  throughput        = 250\n"
        "\n"
        "  tags = {\n"
    ) in found.content
    assert found.said == ('`type` set to "gp3"', "`iops` added, 6000", "`throughput` added, 250")


def test_a_block_with_no_type_gains_one_and_an_unaligned_file_keeps_its_own_spacing() -> None:
    text = 'resource "aws_ebs_volume" "data" {\n  availability_zone = var.az\n  size = 100\n}\n'
    found = edited(text)
    assert found.content == (
        'resource "aws_ebs_volume" "data" {\n'
        '  type = "gp3"\n'
        "  availability_zone = var.az\n"
        "  size = 100\n"
        "}\n"
    )


def test_a_literal_iops_already_there_is_set_to_what_gp3_needs() -> None:
    text = 'resource "aws_ebs_volume" "data" {\n  type = "gp2"\n  iops = 3000\n}\n'
    found = edited(text, Gp3Figures(iops=4000, mibps=125))
    assert "  iops = 4000\n" in found.content
    assert "`iops` set to 4000" in found.said


def test_a_block_commented_out_or_inside_a_string_is_not_a_second_declaration() -> None:
    text = (
        '/*\nresource "aws_ebs_volume" "data" {\n  type = "gp2"\n}\n*/\n'
        '# resource "aws_ebs_volume" "data" {\n'
        'locals { note = "resource \\"aws_ebs_volume\\" \\"data\\" {" }\n'
        'resource "aws_ebs_volume" "data" {\n  type = "gp2"\n}\n'
    )
    assert edited(text).content.endswith('resource "aws_ebs_volume" "data" {\n  type = "gp3"\n}\n')


def test_the_volume_is_found_among_the_folders_files() -> None:
    files = (
        RepositoryFile("storage/providers.tf", 'provider "aws" {\n  region = "eu-west-1"\n}\n'),
        RepositoryFile("storage/volumes.tf", STORAGE),
    )
    found = edit_volume(files, ADDRESS, INCLUDED)
    assert isinstance(found, Edited)
    assert found.path == "storage/volumes.tf"


def block(*body: str) -> str:
    return 'resource "aws_ebs_volume" "data" {\n' + "".join(f"  {line}\n" for line in body) + "}\n"


@pytest.mark.parametrize(
    ("text", "figures", "address", "says"),
    [
        (STORAGE, Gp3Figures(None, None), ADDRESS, "does not record the IOPS"),
        (STORAGE, INCLUDED, 'aws_ebs_volume.data["a"]', "one instance"),
        (STORAGE, INCLUDED, "module.disks.aws_ebs_volume.data", "inside a module"),
        (STORAGE, INCLUDED, "aws_instance.web", "is not an aws_ebs_volume block"),
        (STORAGE, INCLUDED, "aws_ebs_volume.other", "No .tf file in the mapped folder declares"),
        ('resource "aws_ebs_volume" "data" { type = "gp2" }\n', INCLUDED, ADDRESS, "one line"),
        (block("type = var.kind"), INCLUDED, ADDRESS, "set by var.kind"),
        (block('type = "gp3"'), INCLUDED, ADDRESS, "already says gp3"),
        (block('type = "gp2"', "iops = 3000"), INCLUDED, ADDRESS, "does not need"),
        (block('type = "gp2"', "iops = local.iops"), MORE, ADDRESS, "not a number"),
        (block("type = lookup(", '  var.kinds, "data"', ")"), INCLUDED, ADDRESS, "spans lines"),
    ],
)
def test_what_the_edit_cannot_read_for_certain_is_refused_with_the_reason(
    text: str, figures: Gp3Figures, address: str, says: str
) -> None:
    assert says in refused((RepositoryFile("storage/main.tf", text),), figures, address)


def test_a_volume_declared_in_two_files_is_refused_naming_both() -> None:
    files = (RepositoryFile("a/one.tf", STORAGE), RepositoryFile("a/two.tf", STORAGE))
    assert "declared more than once, in a/one.tf, a/two.tf" in refused(files, INCLUDED, ADDRESS)


def test_the_pull_request_carries_the_edit_where_the_file_already_is() -> None:
    recommendation = RecommendationFacts(
        recommendation_id="rec-7",
        waste_class=WasteClass.EBS_GP2_TO_GP3,
        resource_id="vol-0abc",
        sub_account_id="111122223333",
        region_id="eu-west-1",
        estimated_monthly_saving=Decimal("12.40"),
        confidence="HIGH",
        rationale="gp3 gives the same for less",
        as_of=datetime(2026, 10, 15, tzinfo=UTC),
    )
    found = edited(STORAGE, MORE)
    draft = author_gp3(recommendation, ADDRESS, found)
    assert draft.title == f"Move {ADDRESS} from gp2 to gp3"
    assert draft.branch == "meter/remediation/rec-7"
    assert draft.reference == "rec-7"
    assert [(one.path, one.content) for one in draft.changes] == [(found.path, found.content)]
    assert "12.40 USD, modelled" in draft.body
    assert "`iops` added, 6000" in draft.body
    assert "ADR-0038" in draft.body
