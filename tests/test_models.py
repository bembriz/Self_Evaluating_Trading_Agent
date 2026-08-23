from infrastructure.database.models import SystemState


def test_system_state_tabla_y_llave_natural() -> None:
    assert SystemState.__tablename__ == "system_state"
    assert SystemState.key.property.columns[0].unique is True


def test_system_state_defaults() -> None:
    st = SystemState(key="trading_mode", value={"mode": "backtest"})
    assert st.key == "trading_mode"
    assert st.value == {"mode": "backtest"}
    # updated_at es un default a nivel de columna: se aplica en el flush/INSERT,
    # no en la construcción del objeto (se verifica en el test de integración).
    assert st.updated_at is None
