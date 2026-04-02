import pytest
from django.utils import timezone
from accounts.models import ConjuntoResidencial, Torre, Usuario
from kislevsmart.models import Visitante, Sala, Reserva, Cuota, Pago


@pytest.fixture(autouse=True)
def simple_staticfiles(settings):
    settings.STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'


@pytest.fixture
def conjunto(db):
    return ConjuntoResidencial.objects.create(
        nombre='Conjunto Test',
        direccion='Calle 1 # 2-3',
        estado=True,
    )


@pytest.fixture
def torre(db, conjunto):
    return Torre.objects.create(
        conjunto=conjunto,
        nombre='Torre A',
        numero_pisos=5,
        aptos_por_piso=4,
    )


@pytest.fixture
def admin(db, conjunto, torre):
    user = Usuario.objects.create_user(
        cedula='11111111',
        nombre='Admin Test',
        email='admin@test.com',
        password='adminpass123',
        conjunto=conjunto,
        torre=torre,
        apartamento='101',
        user_type='administrador',
    )
    return user


@pytest.fixture
def propietario(db, conjunto, torre):
    user = Usuario.objects.create_user(
        cedula='22222222',
        nombre='Propietario Test',
        email='prop@test.com',
        password='proppass123',
        conjunto=conjunto,
        torre=torre,
        apartamento='201',
        user_type='propietario',
    )
    return user


@pytest.fixture
def portero(db, conjunto):
    user = Usuario.objects.create_user(
        cedula='33333333',
        nombre='Portero Test',
        email='portero@test.com',
        password='porteropass123',
        conjunto=conjunto,
        user_type='porteria',
    )
    return user


@pytest.fixture
def visitante(db, conjunto, admin):
    import uuid
    return Visitante.objects.create(
        nombre='Juan Pérez',
        email='juan@test.com',
        celular='3001234567',
        cedula='44444444',
        motivo='Visita familiar',
        token=str(uuid.uuid4()),
        email_creador=admin.email,
        nombre_log=admin.email,
        numper='201',
        conjunto=conjunto,
    )


@pytest.fixture
def sala(db):
    return Sala.objects.create(
        nombre='Salón Social',
        capacidad=50,
        estado=True,
    )


@pytest.fixture
def cuota(db, conjunto):
    from datetime import date, timedelta
    return Cuota.objects.create(
        conjunto=conjunto,
        nombre='Administración Test',
        monto=200000,
        periodicidad='mensual',
        fecha_vencimiento=date.today() + timedelta(days=30),
    )
