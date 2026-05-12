# Claim Template Layout Diagnostics

Template inspected: `data\docx_templates_v2\manual_claim_template_v2.docx`

## Summary

- Paragraphs: 34
- Tables: 1
- Claimant details appear to be in ordinary paragraphs: Yes

## Paragraphs Containing More Than One Placeholder

- Paragraph 6: `	Highest qualification: {{ highest_qualification }}	 	                                 Budget Allocation: {{ budget_allocation }}`
- Paragraph 8: `	Personnel Number: {{ staff_number }}				                  Tariff per hour: {{ tariff_per_hour }}`
- Paragraph 10: `	Identity / Passport Number: {{ id_or_passport_number }}	                  PAYE No.: {{ paye_number }}`
- Paragraph 12: `Address: {{ physical_address }}     		                                               Tel. no.: {{ contact_number }}`
- Paragraph 17: `
Course/Post: {{ course_post }}	                                                          Faculty/Department: {{ faculty_department }}`

## Paragraphs Mixing Left And Right Claimant Fields

- Paragraph 6: `	Highest qualification: {{ highest_qualification }}	 	                                 Budget Allocation: {{ budget_allocation }}`
- Paragraph 8: `	Personnel Number: {{ staff_number }}				                  Tariff per hour: {{ tariff_per_hour }}`
- Paragraph 10: `	Identity / Passport Number: {{ id_or_passport_number }}	                  PAYE No.: {{ paye_number }}`
- Paragraph 12: `Address: {{ physical_address }}     		                                               Tel. no.: {{ contact_number }}`

## Long-Replacement Reflow Risks

- Paragraph 6: {{ highest_qualification }}
  - Text: `	Highest qualification: {{ highest_qualification }}	 	                                 Budget Allocation: {{ budget_allocation }}`
- Paragraph 10: {{ id_or_passport_number }}, {{ paye_number }}
  - Text: `	Identity / Passport Number: {{ id_or_passport_number }}	                  PAYE No.: {{ paye_number }}`
- Paragraph 12: {{ physical_address }}, {{ contact_number }}
  - Text: `Address: {{ physical_address }}     		                                               Tel. no.: {{ contact_number }}`

## Risky Placeholder Table-Cell Occurrences

- `{{ highest_qualification }}`: 0
- `{{ physical_address }}`: 0
- `{{ id_or_passport_number }}`: 0
- `{{ paye_number }}`: 0
- `{{ contact_number }}`: 0

## Assessment

The detected claimant-detail placeholders are risky when they sit in ordinary paragraphs with tabs or spaces. Long replacement values can cause Word to reflow the paragraph, which may move right-hand fields such as Budget Allocation, Tariff per hour, PAYE No., and Tel. no. out of alignment.
