from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Township(Base):
    __tablename__ = "townships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(11), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_my: Mapped[str | None] = mapped_column(String(255))

    wards: Mapped[list["Ward"]] = relationship("Ward", back_populates="township")
    villages: Mapped[list["Village"]] = relationship("Village", back_populates="township")


class Ward(Base):
    __tablename__ = "wards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(11), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_my: Mapped[str | None] = mapped_column(String(255))
    township_id: Mapped[int] = mapped_column(Integer, ForeignKey("townships.id"), nullable=False)

    township: Mapped["Township"] = relationship("Township", back_populates="wards")


class Village(Base):
    __tablename__ = "villages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(11), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_my: Mapped[str | None] = mapped_column(String(255))
    township_id: Mapped[int] = mapped_column(Integer, ForeignKey("townships.id"), nullable=False)

    township: Mapped["Township"] = relationship("Township", back_populates="villages")


class ICD10Code(Base):
    __tablename__ = "icd10_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(11), unique=True, nullable=False)
    code: Mapped[str | None] = mapped_column(String(50))       # DHIS2 numeric key
    icd_code: Mapped[str | None] = mapped_column(String(20))   # e.g. "A00.0"
    name: Mapped[str] = mapped_column(String(500), nullable=False)
