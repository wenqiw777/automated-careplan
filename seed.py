"""
Run with: python manage.py shell < seed.py
"""
from care_plan.models import Patient, Provider, Order, CarePlan

# Clear existing data
CarePlan.objects.all().delete()
Order.objects.all().delete()
Patient.objects.all().delete()
Provider.objects.all().delete()

# --- Patients ---
alice = Patient.objects.create(name="Alice Johnson", mrn="MRN-001", dob="1980-04-15")
bob = Patient.objects.create(name="Bob Martinez", mrn="MRN-002", dob="1965-11-30")
carol = Patient.objects.create(name="Carol Chen", mrn="MRN-003", dob="1992-07-22")

# --- Providers ---
dr_smith = Provider.objects.create(name="Dr. Sarah Smith", npi="1234567890")
dr_lee = Provider.objects.create(name="Dr. James Lee", npi="0987654321")

# --- Orders ---
order1 = Order.objects.create(
    patient=alice,
    provider=dr_smith,
    medication="Humira 40mg/0.4mL",
    diagnosis="Rheumatoid Arthritis",
    medical_record="Patient reports joint pain and swelling for 6 months. ESR elevated.",
)
order2 = Order.objects.create(
    patient=bob,
    provider=dr_smith,
    medication="Revlimid 25mg",
    diagnosis="Multiple Myeloma",
    medical_record="Newly diagnosed. Prior chemo: none. Renal function within normal limits.",
)
order3 = Order.objects.create(
    patient=carol,
    provider=dr_lee,
    medication="Enbrel 50mg/mL",
    diagnosis="Plaque Psoriasis",
    medical_record="Moderate-to-severe plaque psoriasis, failed topical therapy.",
)

# --- Care Plans (一个 order 有多个，演示 1:many) ---
CarePlan.objects.create(
    order=order1,
    content="[First attempt - failed due to API timeout]",
    status=CarePlan.Status.FAILED,
)
CarePlan.objects.create(
    order=order1,
    content="Patient should self-inject Humira every 2 weeks. Monitor for injection site reactions. Follow up in 4 weeks.",
    status=CarePlan.Status.COMPLETED,
)
CarePlan.objects.create(
    order=order2,
    content="",
    status=CarePlan.Status.PENDING,
)
CarePlan.objects.create(
    order=order3,
    content="Administer Enbrel 50mg once weekly. Baseline TB test required before first dose.",
    status=CarePlan.Status.COMPLETED,
)

print("Seed complete.")
print(f"  Patients: {Patient.objects.count()}")
print(f"  Providers: {Provider.objects.count()}")
print(f"  Orders: {Order.objects.count()}")
print(f"  Care Plans: {CarePlan.objects.count()}")
