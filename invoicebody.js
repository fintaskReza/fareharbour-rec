// =================================================================
// Universal Invoice Script v10 (Adds CustomField)
// =================================================================

// --- Main Data and Debug Initialization ---
const invoiceLineItems = [];
const canonicalChargesFinalized = new Map();
const aggregatedCustomerBookings = new Map();
const FALLBACK_QBO_ITEM_ID = "GENERIC_SALES_ITEM_ID_PLACEHOLDER";

const debug = {
  startTime: new Date().toISOString(),
  scriptStatus: 'started',
  // ... other debug fields
};

// --- Helper Functions (Unchanged) ---
function getCanonicalChargeName(rawName) {
  let canonicalName = rawName.toLowerCase();
  if (canonicalName.includes("stewardship fee")) return "stewardship fee";
  if (canonicalName.includes("fuel surcharge") || canonicalName.includes("field surcharge")) return "fuel surcharge";
  if (canonicalName.includes("bc park fee")) return "bc park fee";
  return canonicalName.replace(/[^a-z0-9]/g, '');
}

function fuzzyMatch(inputName, qboItems) {
  const normalizedInput = inputName.toLowerCase().replace(/[^a-z0-9]/g, '');
  for (const qboItem of qboItems) {
    const normalizedQboName = qboItem.Name.toLowerCase().replace(/[^a-z0-9]/g, '');
    if (normalizedQboName.includes(normalizedInput) || normalizedInput.includes(normalizedQboName)) {
      return qboItem.Id;
    }
  }
  return null;
}

// --- Main Logic ---
try {
  // --- Step 1, 2, 3: Data parsing and condition checking (Unchanged) ---
  const primaryData = items[0]?.json;
  const qboItemsList = [];
  for (let i = 1; i < items.length; i++) {
    if (items[i].json?.Name && items[i].json?.Id) {
      qboItemsList.push(items[i].json);
    }
  }

  const bookingData = primaryData?.body?.booking;
  if (!bookingData) throw new Error('Booking data not found in items[0].json.body.booking');

  debug.foundBookingData = true;
  debug.bookingUUID = bookingData.uuid;
  const rebookedFromUuid = bookingData.rebooked_from;
  debug.isRebooking = !!rebookedFromUuid;
  debug.rebookedFromUUID = rebookedFromUuid || null;
  
  let isRebookMatch = false;
  if (rebookedFromUuid && primaryData?.CustomerMemo?.value?.includes(rebookedFromUuid)) {
    isRebookMatch = true;
    debug.foundMatchingInvoice = true;
  }
  const isUpdateNeededByFlag = primaryData?.reconciliation?.isInvoiceUpdateNeeded === true;
  debug.isUpdateNeededByFlag = isUpdateNeededByFlag;

  // --- Step 4: Build line items, including discounts (Unchanged) ---
    const allCustomFields = [];
    if (bookingData.availability?.custom_field_instances) {
        bookingData.availability.custom_field_instances.forEach(inst => inst.custom_field && allCustomFields.push(inst.custom_field));
    }
    if (bookingData.customers) {
        bookingData.customers.forEach(customer => customer.custom_field_values?.forEach(val => {
            if (val.custom_field && (val.custom_field.type !== 'yes-no' || val.value === 'True')) {
                allCustomFields.push(val.custom_field);
            }
        }));
    }

    allCustomFields.forEach(customField => {
      if (customField && typeof customField.offset === 'number' && customField.offset > 0) {
        const canonicalName = getCanonicalChargeName(customField.name);
        let quantity = customField.is_always_per_customer ? (bookingData.customer_count || 1) : 1;
        if (canonicalChargesFinalized.has(canonicalName)) {
          canonicalChargesFinalized.get(canonicalName).quantity += quantity;
        } else {
          canonicalChargesFinalized.set(canonicalName, {
            originalName: customField.name, unitPrice: customField.offset, quantity: quantity,
          });
        }
      }
    });

    canonicalChargesFinalized.forEach((chargeInfo, name) => {
      const qboItemId = fuzzyMatch(chargeInfo.originalName, qboItemsList);
      const unitPriceConverted = chargeInfo.unitPrice / 100;
      invoiceLineItems.push({
        DetailType: "SalesItemLineDetail", Amount: unitPriceConverted * chargeInfo.quantity,
        SalesItemLineDetail: { 
          ItemRef: { value: qboItemId || FALLBACK_QBO_ITEM_ID, name: chargeInfo.originalName }, 
          Qty: chargeInfo.quantity, UnitPrice: unitPriceConverted, TaxCodeRef: { value: "3" },
          ClassRef: { value: "572487" }
        },
        Description: chargeInfo.originalName
      });
    });

    if (Array.isArray(bookingData.customers)) {
      bookingData.customers.forEach(customer => {
        const prototype = customer.customer_type_rate?.customer_prototype;
        if (prototype) {
          const key = prototype.display_name;
          // Use prototype.total first, but fall back to customer.total_cost.price for cases like Private Charter
          let unitPrice = (prototype.total || 0) / 100;
          if (unitPrice === 0 && customer.total_cost?.price) {
            unitPrice = customer.total_cost.price / 100;
          }
          
          if (aggregatedCustomerBookings.has(key)) {
            const existing = aggregatedCustomerBookings.get(key);
            // For variable pricing (like Private Charter), calculate weighted average
            const existingTotal = existing.SalesItemLineDetail.UnitPrice * existing.SalesItemLineDetail.Qty;
            const newTotal = existingTotal + unitPrice;
            const newQty = existing.SalesItemLineDetail.Qty + 1;
            existing.SalesItemLineDetail.Qty = newQty;
            existing.SalesItemLineDetail.UnitPrice = newTotal / newQty;
          } else {
            aggregatedCustomerBookings.set(key, { DetailType: "SalesItemLineDetail", SalesItemLineDetail: { ItemRef: { name: key }, Qty: 1, UnitPrice: unitPrice, TaxCodeRef: { value: "3" }}});
          }
        }
      });
    }

    const mainBookingItemName = bookingData.availability?.item?.name || "Unknown Booking";
    const mainBookingQboId = fuzzyMatch(mainBookingItemName, qboItemsList);
    aggregatedCustomerBookings.forEach((customerBookingItem, key) => {
      const lineAmount = customerBookingItem.SalesItemLineDetail.UnitPrice * customerBookingItem.SalesItemLineDetail.Qty;
      invoiceLineItems.push({
        DetailType: "SalesItemLineDetail", Amount: lineAmount,
        SalesItemLineDetail: { 
          ItemRef: { value: mainBookingQboId || FALLBACK_QBO_ITEM_ID, name: mainBookingItemName }, 
          Qty: customerBookingItem.SalesItemLineDetail.Qty, UnitPrice: customerBookingItem.SalesItemLineDetail.UnitPrice, TaxCodeRef: customerBookingItem.SalesItemLineDetail.TaxCodeRef,
          ClassRef: { value: "572487" }
        },
        Description: `${mainBookingItemName} - ${key}`
      });
    });
  
    // Check if calculated total matches expected total, if not apply fallback logic
    let calculatedGrossSubtotal = invoiceLineItems.reduce((total, line) => {
      if (line.DetailType === "SalesItemLineDetail") { return total + line.Amount; } return total;
    }, 0);
    const bookingNetSubtotal = bookingData.receipt_subtotal / 100;
    
    // Fallback: If totals don't match, try passenger-based fee calculation for Private Charter
    if (Math.abs(calculatedGrossSubtotal - bookingNetSubtotal) > 0.01) {
      debug.fallbackTriggered = true;
      debug.calculatedBeforeFallback = calculatedGrossSubtotal;
      
      // Look for Private Charter bookings with passenger counts
      if (Array.isArray(bookingData.customers)) {
        bookingData.customers.forEach(customer => {
          const isPrivateCharter = customer.customer_type_rate?.customer_prototype?.display_name === "Private Charter";
          
          if (isPrivateCharter && customer.custom_field_values) {
            // Extract passenger counts from custom field values
            const passengerCounts = {};
            customer.custom_field_values.forEach(fieldValue => {
              if (fieldValue.name === "Adults" || fieldValue.name === "Youths" || 
                  fieldValue.name === "Children" || fieldValue.name === "Seniors") {
                const count = parseInt(fieldValue.value) || 0;
                if (count > 0) {
                  passengerCounts[fieldValue.name] = count;
                }
              }
            });
            
            // Apply per-passenger fees from availability settings
            Object.entries(passengerCounts).forEach(([passengerType, count]) => {
              // Map passenger type names to customer type rates
              const customerTypeMapping = {
                "Adults": "Adult", "Youths": "Youth", 
                "Children": "Child", "Seniors": "Senior"
              };
              const mappedType = customerTypeMapping[passengerType];
              
              if (mappedType && bookingData.availability?.customer_type_rates) {
                const customerTypeRate = bookingData.availability.customer_type_rates.find(
                  rate => rate.customer_prototype?.display_name === mappedType
                );
                
                if (customerTypeRate?.custom_field_instances) {
                  customerTypeRate.custom_field_instances.forEach(instance => {
                    const customField = instance.custom_field;
                    if (customField && customField.offset > 0) {
                      const canonicalName = getCanonicalChargeName(customField.name);
                      const unitPrice = customField.offset / 100;
                                             const totalQuantity = count; // For fallback, always use passenger count
                      
                      // Check if we already have this charge, if so add to it
                      const existingLineIndex = invoiceLineItems.findIndex(
                        line => line.Description === customField.name
                      );
                      
                      if (existingLineIndex >= 0) {
                        invoiceLineItems[existingLineIndex].SalesItemLineDetail.Qty += totalQuantity;
                        invoiceLineItems[existingLineIndex].Amount += unitPrice * totalQuantity;
                      } else {
                        const qboItemId = fuzzyMatch(customField.name, qboItemsList);
                        invoiceLineItems.push({
                          DetailType: "SalesItemLineDetail",
                          Amount: unitPrice * totalQuantity,
                          SalesItemLineDetail: {
                            ItemRef: { value: qboItemId || FALLBACK_QBO_ITEM_ID, name: customField.name },
                            Qty: totalQuantity,
                            UnitPrice: unitPrice,
                            TaxCodeRef: { value: "3" },
                            ClassRef: { value: "572487" }
                          },
                          Description: customField.name
                        });
                      }
                    }
                  });
                }
              }
            });
          }
        });
      }
      
      // Recalculate total after fallback
      calculatedGrossSubtotal = invoiceLineItems.reduce((total, line) => {
        if (line.DetailType === "SalesItemLineDetail") { return total + line.Amount; } return total;
      }, 0);
      debug.calculatedAfterFallback = calculatedGrossSubtotal;
    }
    
    const totalDiscount = calculatedGrossSubtotal - bookingNetSubtotal;
    debug.totalDiscountCalculated = totalDiscount;
    if (totalDiscount > 0.01) {
      invoiceLineItems.push({
        Amount: totalDiscount, DetailType: "DiscountLineDetail",
        DiscountLineDetail: { 
          PercentBased: false,
          ClassRef: { value: "572487" }
        }, 
        Description: "Applied Booking Discounts"
      });
    }

  // --- Step 5: Final Assembly ---
  const correctSubtotal = bookingData.receipt_subtotal / 100;
  const correctTaxTotal = bookingData.receipt_taxes / 100;
  const txnTaxDetail = {
    TotalTax: correctTaxTotal, TaxLine: [{
      Amount: correctTaxTotal, DetailType: "TaxLineDetail",
      TaxLineDetail: {
        NetAmountTaxable: correctSubtotal, TaxRateRef: { value: "4" }, PercentBased: true, TaxPercent: 5,
      }
    }]
  };
  
  // *** NEW: Define the Custom Field payload once ***
  const customFieldPayload = [{
    DefinitionId: "1",
    Name: "FH booking ID",
    Type: "StringType",
    StringValue: String(bookingData.pk) // Use the booking pk and ensure it's a string
  }];

  let finalPayload;
  
  if (isRebookMatch || isUpdateNeededByFlag) {
    const invoiceToUpdate = primaryData;
    if (!invoiceToUpdate?.Id || !invoiceToUpdate?.SyncToken) {
      throw new Error(`An update was triggered, but no valid Invoice ID or SyncToken was found in the input.`);
    }

    debug.finalAction = 'UPDATE_INVOICE';
    debug.scriptStatus = 'Success';
    
    finalPayload = {
      sparse: true,
      Id: invoiceToUpdate.Id,
      SyncToken: invoiceToUpdate.SyncToken,
      DocNumber: `FH-${(bookingData.uuid).slice(-12)}`,
      CustomerMemo: { value: `Booking UUID: ${bookingData.uuid}\nBooking Number: #${bookingData.pk}` },
      Line: invoiceLineItems,
      TxnTaxDetail: txnTaxDetail,
      CustomField: customFieldPayload // <-- ADDED THIS LINE
    };
  } else {
    debug.finalAction = 'CREATE_INVOICE';
    if (rebookedFromUuid) {
      debug.scriptStatus = 'Warning: Rebooking without a found invoice. Creating a new one.';
    } else {
      debug.scriptStatus = 'Success';
    }
    
    finalPayload = {
      DocNumber: `FH-${(bookingData.uuid).slice(-12)}`,
      TxnDate: new Date(bookingData.created_at).toISOString().split('T')[0],
      CustomerRef: { value: "2" },
      Line: invoiceLineItems,
      CustomerMemo: { value: `Booking UUID: ${bookingData.uuid}` },
      GlobalTaxCalculation: "TaxExcluded",
      TxnTaxDetail: txnTaxDetail,
      CustomField: customFieldPayload // <-- ADDED THIS LINE
    };
  }
  
  return [{ json: { invoiceDataBody: finalPayload, debug: debug } }];

} catch (e) {
  debug.scriptStatus = 'Critical Error';
  debug.error = e.message;
  return [{ json: { message: "A critical error occurred.", error: e.message, stack: e.stack, debug: debug } }];
}