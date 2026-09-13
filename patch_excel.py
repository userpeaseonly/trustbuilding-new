import re

with open('contract/views.py', 'r') as f:
    content = f.read()

new_view = """
@login_required
def download_payments_excel(request, pk):
    \"\"\"Download the payment history as an Excel file.\"\"\"
    company = get_user_company(request.user)
    contract = get_object_or_404(Contract, pk=pk, company=company)
    
    # Create an Excel workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Payments"
    
    # Headers
    headers = ['ID', 'Sana', 'Summa', 'To\\'lov turi', 'Tranzaksiya ID', 'Xodim']
    ws.append(headers)
    
    # Style the header row
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = openpyxl.styles.Font(bold=True)
    
    # Fetch logs
    payment_logs = contract.payment_logs.all().order_by('-date_paid')
    
    for log in payment_logs:
        staff_name = "Noma'lum"
        try:
            # We assume added_by or similar exists, otherwise leave blank
            pass
        except:
            pass
            
        ws.append([
            log.id,
            log.date_paid.strftime("%d.%m.%Y %H:%M"),
            float(log.amount),
            log.get_payment_type_display(),
            log.transaction_id or '',
            ''
        ])
        
    # Return response
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Payments_{contract.id}.xlsx"'
    wb.save(response)
    return response

"""

parts = content.split('def download_docx_contract(request, pk):')
if len(parts) == 2:
    subparts = parts[1].split('@login_required\ndef receipt_view', 1)
    if len(subparts) == 2:
        new_content = parts[0] + 'def download_docx_contract(request, pk):' + subparts[0] + new_view + '\n@login_required\ndef receipt_view' + subparts[1]
        with open('contract/views.py', 'w') as f:
            f.write(new_content)
        print("Success")
    else:
        print("Could not find receipt_view")
else:
    print("Could not find download_docx_contract")

