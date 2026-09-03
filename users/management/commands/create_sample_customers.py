import random
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from users.models import CustomUser

class Command(BaseCommand):
    help = "Generate sample customer records for testing and demonstration"

    def add_arguments(self, parser):
        parser.add_argument(
            '--count',
            type=int,
            default=10,
            help='Number of sample customers to create (default: 10)'
        )

    def handle(self, *args, **options):
        count = options['count']
        
        sample_data = [
            {"name": "Alisher Tursunov", "gender": "M", "phone": "+998901234501"},
            {"name": "Dilnoza Vahobova", "gender": "F", "phone": "+998901234502"},
            {"name": "Jamshid Alimov", "gender": "M", "phone": "+998912345603"},
            {"name": "Nigora Hasanova", "gender": "F", "phone": "+998933456704"},
            {"name": "Sardor Rahimov", "gender": "M", "phone": "+998944567805"},
            {"name": "Malika Umarova", "gender": "F", "phone": "+998975678906"},
            {"name": "Bekzod Karimov", "gender": "M", "phone": "+998996789007"},
            {"name": "Shahlo Mahmudova", "gender": "F", "phone": "+998907890108"},
            {"name": "Javohir Toshpulatov", "gender": "M", "phone": "+998918901209"},
            {"name": "Zuhra Yusupova", "gender": "F", "phone": "+998939012310"},
            {"name": "Otabek Qodirov", "gender": "M", "phone": "+998940123411"},
            {"name": "Feruza Abduvaliyeva", "gender": "F", "phone": "+998971234512"},
            {"name": "Sherzod Boboyev", "gender": "M", "phone": "+998992345613"},
            {"name": "Gulnora Nazarova", "gender": "F", "phone": "+998903456714"},
            {"name": "Bobur Mirzayev", "gender": "M", "phone": "+998914567815"},
        ]

        districts = [
            "Toshkent sh. Yunusobod tuman IIB",
            "Toshkent sh. Mirzo Ulug'bek tuman IIB",
            "Toshkent sh. Chilonzor tuman IIB",
            "Toshkent sh. Shayxontohur tuman IIB",
            "Toshkent sh. Yakkasaroy tuman IIB",
            "Samarqand sh. IIB",
            "Buxoro sh. IIB",
            "Andijon sh. IIB",
        ]

        created_count = 0
        existing_count = 0

        for i in range(count):
            if i < len(sample_data):
                item = sample_data[i]
                full_name = item["name"]
                gender = item["gender"]
                phone = item["phone"]
            else:
                # Generate fallback data for extra requested count
                suffix = f"{100 + i}"
                phone = f"+998900000{suffix}"
                gender = "M" if i % 2 == 0 else "F"
                full_name = f"Mijoz Testov {i+1}"

            passport_letters = random.choice(["AA", "AB", "AC", "AD"])
            passport_numbers = f"{random.randint(1000000, 9999999)}"
            passport_series = f"{passport_letters}{passport_numbers}"

            pinfl = f"3{random.randint(10, 31)}{random.randint(10, 12)}{random.randint(50, 99)}{random.randint(100000, 999999)}"
            issued_by = random.choice(districts)
            
            # Random issue date between 1 to 10 years ago
            days_ago = random.randint(300, 3650)
            issue_date = date.today() - timedelta(days=days_ago)

            user, created = CustomUser.objects.get_or_create(
                phone_number=phone,
                defaults={
                    'full_name': full_name,
                    'gender': gender,
                    'is_customer': True,
                    'passport_series': passport_series,
                    'passport_jshshr': pinfl,
                    'passport_issued_by': issued_by,
                    'passport_date_of_issue': issue_date,
                    'status': True,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  [+] Created customer: {full_name} ({phone}) | Passport: {passport_series}"))
            else:
                existing_count += 1
                # Ensure is_customer flag is active
                if not user.is_customer:
                    user.is_customer = True
                    user.save(update_fields=['is_customer'])
                self.stdout.write(self.style.WARNING(f"  [*] Already exists: {full_name} ({phone})"))

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Successfully processed {count} customer records ({created_count} created, {existing_count} existing)."))
