"""Thêm messages.seq để giữ đúng thứ tự lượt hỏi - đáp.

Trước đó lịch sử hội thoại sắp theo ``created_at``, nhưng ``now()`` của
PostgreSQL trả về thời điểm bắt đầu transaction: câu hỏi và câu trả lời được ghi
trong cùng một request nên có ``created_at`` bằng nhau và thứ tự trở thành ngẫu
nhiên. Identity column cho thứ tự chèn tuyệt đối.

Revision ID: 6af0dc6c41f3
Revises: 5fa216d0d09f
Create Date: 2026-08-26 01:17:39.397335

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6af0dc6c41f3'
down_revision: Union[str, Sequence[str], None] = '5fa216d0d09f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Message có sẵn được cấp seq theo created_at rồi tới id, nên hội thoại cũ
    # giữ nguyên thứ tự đang hiển thị thay vì bị đảo lộn ngẫu nhiên.
    op.add_column(
        "messages",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
    )
    op.execute(
        """
        WITH ordered AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS position
            FROM messages
        )
        UPDATE messages
        SET seq = ordered.position
        FROM ordered
        WHERE messages.id = ordered.id
        """
    )
    # Identity vẫn đang ở 1 sau khi ghi đè bằng UPDATE; đẩy lên quá giá trị lớn
    # nhất để message mới không đụng seq đã dùng.
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('messages', 'seq'),
            GREATEST((SELECT COALESCE(MAX(seq), 0) FROM messages), 1)
        )
        """
    )
    op.create_index(op.f("ix_messages_seq"), "messages", ["seq"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_messages_seq"), table_name="messages")
    op.drop_column("messages", "seq")
