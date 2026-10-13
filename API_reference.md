Sales Orders API
The Sales Orders API is used to manage sales order data.

Operation
Description
Method
https://connect.plex.com/sales/v1/orders
Create a customer purchase order.
POST
https://connect.plex.com/sales/v1/orders/{id}/lines
Add a new sales order line.
POST
https://connect.plex.com/sales/v1/orders/{id}/lines/{lineId}/approved-ship-tos
Create a sales order line's approved Ship To address.
POST
https://connect.plex.com/sales/v1/orders/{id}/lines/{lineId}/prices
Add price to a sales order line.
POST
https://connect.plex.com/sales/v1/orders/{id}
Retrieve a sales order by ID.
GET
https://connect.plex.com/sales/v1/orders/{id}/lines/{lineId}
Retrieve a sales order line by line ID.
GET
https://connect.plex.com/sales/v1/orders/{id}/lines/{lineId}/prices/{priceId}
Retrieve a sales order line's price by its price ID.
GET
https://connect.plex.com/sales/v1/orders/{id}/lines/{lineId}/price-adjustments
List Order Line Price Adjustments by query parameters.
GET
https://connect.plex.com/sales/v1/orders/{id}/price-adjustments
List Order Price Adjustments by query parameters.
GET
https://connect.plex.com/sales/v1/orders/{id}/lines/{lineId}/approved-ship-tos
List the sales order line's approved Ship To addresses by ID.
GET
https://connect.plex.com/sales/v1/orders/{id}/lines/{lineId}/prices
Get a list of sales order line prices by the line ID.
GET
https://connect.plex.com/sales/v1/orders/{id}/lines
List sales order lines by sales order ID.
GET
https://connect.plex.com/sales/v1/orders
List Sales Orders by query parameters.
GET
https://connect.plex.com/sales/v1/orders/{id}
Update a customer purchase order.
PUT
https://connect.plex.com/sales/v1/orders/{id}/line/{lineId}
Update a sales order line.
PUT
https://connect.plex.com/sales/v1/orders/{id}/lines/{lineId}/prices/{priceId}
Update a price on a sales order line.
PUT


Purchase Orders API
The Purchase Orders API is used to retrieve purchase order information, including line items. This API exposes endpoints to retrieve purchase orders and their sub-resources in the context of Purchasing. Use a GET request to retrieve the information about purchase orders, line items related to purchase orders, purchase order types, and statuses.

Operation
Description
Method
https://connect.plex.com/purchasing/v1/purchase-orders/{id}/line-items/{lineItemId}
Retrieve a PO line item by ID. A line item on a purchase order contains information that specifies the purchased item or service along with the low-level details of the order, including the price (depending on configuration) and release schedule. Most of the fields available in a line item are controlled by the PO type. Some fields are also controlled by module settings and setup table configuration.
GET
https://connect.plex.com/purchasing/v1/purchase-orders/{id}
Retrieve a purchase order by ID. Purchase orders (POs) are created for single-use "spot buys" or recurring blanket orders of goods from suppliers. Before using POs to order goods (such as parts, materials, and supplies), the goods must be defined in the system. For example, a component part must appear on the Parts screen to order it from a supplier. Once the purchase order is created in the system, Get Purchase Order is used to retrieve the purchase order information.
GET
https://connect.plex.com/purchasing/v1/purchase-orders/{poId}/line-items
List PO line items by query parameters. The List Line Items operation retrieves the information associated with the line items. PO line items are used to specify the purchased item or service along with the low-level details of the order, including the price (depending on configuration) and release schedule. Most of the fields available in a line item are controlled by the PO type. Some fields are also controlled by module settings and setup table configuration.
GET
https://connect.plex.com/purchasing/v1/purchase-orders/{id}/line-items/{lineItemId}/prices
List purchase order prices based on specified query parameters related to the price's effective date and expiration date.
GET
https://connect.plex.com/purchasing/v1/purchase-order-statuses
List purchase order statuses based on specified PO status properties. Purchase order status can include values such as New, Requested, Review, On order, Approved, Hold, Cancelled, Received, or other custom statuses as configured in the PO Status setup table.
GET
https://connect.plex.com/purchasing/v1/purchase-order-types
List purchase order type records based on specified PO type properties. Purchase order types can include values such as Direct Materials, Purchased Components and Materials, Subcontract, Inventoried MRO / Supply, Indirect Services, Tooling, CapEx, or other custom types as configured on the Purchase Order Types screen.
GET
https://connect.plex.com/purchasing/v1/purchase-orders
List purchase orders by query parameters. Purchase orders (POs) are created for single-use "spot buys" or recurring blanket orders of goods from suppliers. Before using POs to order goods (such as parts, materials, and supplies), the goods must be defined in the system. For example, a component part must appear on the Parts screen before ordering it from a supplier.
GET


Parts API
The Parts API is used to manage part master data.

Operation
Description
Method
https://connect.plex.com/mdm/v2/parts
Create a new part.
POST
https://connect.plex.com/mdm/v2/parts/{id}
Delete a part.
DELETE
https://connect.plex.com/mdm/v2/parts/{id}
Retrieve a part by ID.
GET
https://connect.plex.com/mdm/v2/parts
List parts by query parameters.
GET
https://connect.plex.com/mdm/v2/parts/sync
Sync a set of parts from another system. This operation performs create and update logic.
POST
https://connect.plex.com/mdm/v2/parts/{id}
Update a part.
PUT

Part Specifications API
The Part Specifications API is used to manage part specifications data.

Operation
Description
Method
https://connect.plex.com/quality/v1/part-specifications/{id}
Retrieve a part specification by ID.
GET
https://connect.plex.com/quality/v1/part-specifications
Retrieve a list of part specifications.
GET

Inventory Tracking API
The Inventory Tracking API is used to manage Inventory Data.

Operation
Description
Method
https://connect.plex.com/inventory-tracking/v1/containers/{serialNumber}
Retrieve a container record based on the specified serial number.
GET
https://connect.plex.com/inventory-tracking/v1/master-units/{id}
Retrieve a master unit record based on the specified ID.
GET
https://connect.plex.com/inventory-tracking/v1/master-units
Retrieve a master unit records.
GET
https://connect.plex.com/inventory-tracking/v1/containers/{serialNo}/rfid
Update container rfid based on specified serial number.
PUT
https://connect.plex.com/inventory-tracking/v1/master-units/{id}/rfid
Update master unit rfid details.
PUT

Employees API
The Employees API is used to manage employee and user master data. Note: Any endpoints that alter data cannot be used if your PCN has been fully migrated to IAM. The Get and List endpoints are still accessible.

Operation
Description
Method
https://connect.plex.com/mdm/v1/employees/{id}/activate
Activate an Employee and the associated User Account. Note: Additional configuration is required via the User Manager to fully enable User login.
POST
https://connect.plex.com/mdm/v1/employees
Create a new Employee and associated User Account (if User ID provided does not already correspond to existing User). Note: Additional configuration required via User Manager to fully enable User login.
POST
https://connect.plex.com/mdm/v1/employees/{id}/deactivate
Deactivate an Employee and the associated User Account.
POST
https://connect.plex.com/mdm/v1/employees/{id}
Retrieve an Employee by Resource ID.
GET
https://connect.plex.com/mdm/v1/employees
List Employees by query parameters.
GET
https://connect.plex.com/mdm/v1/employees/sync
Sync a set of Employees from another system. This operation creates Employees that do not exist in Plex and updates existing Employees.
POST
https://connect.plex.com/mdm/v1/employees/{id}/transfer
Transfer an Employee to a different Tenant within the same Enterprise. Note: The Employee setup data must be available in the target Tenant in order for the Employee to transfer successfully.
POST
https://connect.plex.com/mdm/v1/employees/{id}
Update an Employee.



Customers API
The Customers API is used to manage customer master data, including financial information and addresses.

Operation
Description
Method
https://connect.plex.com/mdm/v1/customers
Create a new customer.
POST
https://connect.plex.com/mdm/v1/customers/{customerId}/addresses
Create a new customer address.
POST
https://connect.plex.com/mdm/v1/customers/{id}/deactivate
Deactivates a customer by changing it's Customer Status to Deleted.
POST
https://connect.plex.com/mdm/v1/customers/{customerId}/addresses/{addressId}
Deletes a customer address.
DELETE
https://connect.plex.com/mdm/v1/customers/{id}
Retrieve a customer by ID.
GET
https://connect.plex.com/mdm/v1/customers/{customerId}/addresses/{addressId}
Retrieve a customer address by ID.
GET
https://connect.plex.com/mdm/v1/customers/{customerId}/addresses/{addressId}/edi-details
Get customer address EDI details.
GET
https://connect.plex.com/mdm/v1/customers/{id}/financials
Retrieve customer financial information by ID.
GET
https://connect.plex.com/mdm/v1/customers/{customerId}/addresses
Get customer addresses by query parameters.
GET
https://connect.plex.com/mdm/v1/customers
List customers by query parameters.
GET
https://connect.plex.com/mdm/v1/customers/sync
Sync a set of customers from another system. This operation creates customers that do not exist in Plex and updates existing customers. This information includes customers addresses and customer financials.
POST
https://connect.plex.com/mdm/v1/customers/{id}
Update a customer.
PUT
https://connect.plex.com/mdm/v1/customers/{customerId}/addresses/{addressId}
Update a customer address.
PUT
https://connect.plex.com/mdm/v1/customers/{customerId}/addresses/{addressId}/edi-details
Update a Customer Address EDI Details.
PUT
https://connect.plex.com/mdm/v1/customers/{id}/financials
Update the financial information for a customer.
PUT

Custom Fields API
The custom fields API to query standard objects, field definitions, field types

Operation
Description
Method
https://connect.plex.com/platform/custom-fields/v1/field-values/delete
Delete custom field values from the list of specified resources.
POST
https://connect.plex.com/platform/custom-fields/v1/field-definitions/{fieldName}
Get Custom Field Definition by Name.
GET
https://connect.plex.com/platform/custom-fields/v1/field-types/{fieldTypeName}
Get a data type and its available constraints that can be assigned to a custom field.
GET
https://connect.plex.com/platform/custom-fields/v1/standard-objects/{standardObjectName}
Get information about a standard object.
GET
https://connect.plex.com/platform/custom-fields/v1/field-definitions
Retrieve a list of custom field definitions and the standard objects to which they have been added.
GET
https://connect.plex.com/platform/custom-fields/v1/field-types
Retrieve a list of data types that can be assigned to a custom field definition.
GET
https://connect.plex.com/platform/custom-fields/v1/standard-objects
Retrieve a list of standard objects and the property keys that uniquely identify records.
GET
https://connect.plex.com/platform/custom-fields/v1/field-values/save
Add or update custom field values for the list of specified resources.
POST
https://connect.plex.com/platform/custom-fields/v1/field-values/search
Retrieve a list of resources of the specified standard object by searching against record identifiers and custom field values.
POST
https://connect.plex.com/platform/custom-fields/v1/field-values/validate
Validate Custom Field Values.
POST

BOM API
The BOM API is used to manage BOM Data.

Operation
Description
Method
https://connect.plex.com/engineering/v1/boms
Create a new BOM Component.
POST
https://connect.plex.com/engineering/v1/boms/{id}/deactivate
Deactivate a BOM Component.
POST
https://connect.plex.com/engineering/v1/boms/{id}
Retrieve a BOM Component by ID.
GET
https://connect.plex.com/engineering/v1/boms
List BOM Components by query parameters.
GET
https://connect.plex.com/engineering/v1/boms/{id}
Patch a BOM Component.
PATCH



Sales Releases API
The Sales Releases API is used to manage sales release data.

Operation
Description
Method
https://connect.plex.com/sales/v1/releases
Create a sales release.
POST
https://connect.plex.com/sales/v1/releases/{id}
Retrieve a sales release record by ID.
GET
https://connect.plex.com/sales/v1/releases/{id}/edi-details
Retrieve a sales release's EDI details.
GET
https://connect.plex.com/sales/v1/releases
List sales release records based on sales release properties.
GET
https://connect.plex.com/sales/v1/releases/{id}
Update a sales release.
PUT
https://connect.plex.com/sales/v1/releases/{id}/edi-details
Update a sales release's EDI details.
PUT


Best Practices Guide
Best practices for using API keys
API keys are required for apps and projects that use Plex APIs. Secure your API keys when you create them for maximum security.

It’s possible to secure API keys after they're created and in use, but there can be different constraints based on how the key is used. Protect against unauthorized access by selecting the products it’s used for and regularly replacing keys.

Restrict API keys
When you first create your API keys, apply API restrictions so they run only on specific APIs. You must have a valid API key to use an API. Limit the usage of API keys to only the necessary APIs. You can specify as many APIs as required.

When creating or editing an API key, you can set the key to expire after a certain amount of time. This helps prevent against unauthorized access by ensuring the API key does not persist longer than needed. After the key expires, you must reset the expiration date or make a new key.

Make sure all your API keys have API restrictions and expiration dates. If you have insecure API keys, create new ones with the appropriate security measures and update all your apps with the new API keys. One key per application provides the most security, but you can use a key on multiple apps if the restrictions on the key don’t cause incompatibility issues with the other apps using that key.

When restricting existing API keys by editing apps, make sure the restrictions don’t break any of your existing apps.

Restrict developer portal account access
Prevent unnecessary API key creating by restricting access to the developer portal. Your Plex champion should grant access only to users who need it.

Regularly audit your API keys
Frequently audit your API keys to confirm they’re being actively used. We recommend auditing your API keys at least every three months. Check the usage of your keys in the analytics tab and delete any unneeded keys to keep your APIs secure.

Use independent API keys for different apps
Limit the scope of each key. If an API key is compromised, you can delete and revoke the impacted key without needing to update your other API keys. Note that the test and production keys must be different keys.

Regenerate API keys regularly
API keys can be created and destroyed without affecting the integrations. Rotating API keys limits the potential impact of an API key that is leaked while still providing access to the resource.

Rotate API keys by performing the following steps:

Create a new API key.
Update the resource or application to use the new API key.
Delete the old API key.
A short time overlap between switching keys ensures a smooth turnover without disrupting integrations.

Create a generic IAM ID for developer portal access
Better control access to API keys by creating a single, generic account for creating API keys. If there are unneeded keys, the admin can repurpose or delete the keys.

Store API keys in a secure location
Store your API keys in environment variables or in files outside of your application’s source tree. Keeping the files outside your application's source tree to help ensure your keys do not end up in your source code control system. This is particularly important if you use a public source code management system such as GitHub. Do not embed API keys directly in code. API keys that are embedded in code can be accidentally exposed to the public if you forget to remove the keys from the code that you share.

Encrypt keys on code repositories
Always encrypt any keys stored on code repositories. When sharing code online, it’s easy to forget your credentials in the code, leaving them exposed to the world. Repositories frequently get cloned and forked into new projects, giving new developers access to their complete history. Any credentials within the repository's history will exist in all new repositories born from that source.