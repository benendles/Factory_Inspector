from app.database.models import Base, EquipmentIdentityVerification
from app.database.session import engine


def main() -> None:
    """
    Create missing SQLAlchemy tables.

    Safe for local development when existing table definitions are
    compatible with the current database schema.

    This does not modify existing tables to match changed model definitions.
    Use a database migration for schema changes in production.
    """
    # Importing EquipmentIdentityVerification registers the model
    # with Base.metadata.
    _ = EquipmentIdentityVerification

    Base.metadata.create_all(bind=engine)

    print(
        "Database table creation completed. "
        "Check PostgreSQL for equipment_identity_verifications."
    )


if __name__ == "__main__":
    main()