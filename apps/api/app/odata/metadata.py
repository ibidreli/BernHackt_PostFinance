"""Static OData v4 `$metadata` CSDL document (T9).

Static, not generated from the Pydantic schemas: the service exposes a
fixed, small set of OData resources (`RecurringPayments`, `Alerts`,
`GetForecast`, `Simulate` from `app/api/routes/forecast.py`), so
hand-writing the CSDL once is simpler and more transparent than building
a schema-to-CSDL generator for a hackathon timeline. Keep this in sync with
`app/schemas/forecast.py` by hand if fields change. The Future-Me
Chatbot (`/api/v1/assistant/*`) is deliberately REST, not OData, and
therefore absent here - see ASSISTANT_API.md.

`RecurringPayment.recurring_id` (the entity key) doesn't exist as a
stored field - it's computed by `recurring_payment_id()` (T3) from
merchant+category+flow. The CSDL still declares it as the key property
because that's what OData clients need to address individual entities;
T10's route computes it the same way when serializing.
"""

from __future__ import annotations

METADATA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
  <edmx:DataServices>
    <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="Forecast">

      <EntityType Name="RecurringPayment">
        <Key><PropertyRef Name="recurring_id"/></Key>
        <Property Name="recurring_id" Type="Edm.String" Nullable="false"/>
        <Property Name="merchant" Type="Edm.String" Nullable="false"/>
        <Property Name="category_main" Type="Edm.String"/>
        <Property Name="category_sub" Type="Edm.String"/>
        <Property Name="amount_chf" Type="Edm.Double" Nullable="false"/>
        <Property Name="interval" Type="Edm.String" Nullable="false"/>
        <Property Name="day_of_month" Type="Edm.Int32"/>
        <Property Name="flow" Type="Edm.String" Nullable="false"/>
        <Property Name="first_seen" Type="Edm.Date" Nullable="false"/>
        <Property Name="last_seen" Type="Edm.Date" Nullable="false"/>
        <Property Name="is_active" Type="Edm.Boolean" Nullable="false"/>
      </EntityType>

      <EntityType Name="Alert">
        <Key><PropertyRef Name="alert_id"/></Key>
        <Property Name="alert_id" Type="Edm.String" Nullable="false"/>
        <Property Name="type" Type="Edm.String" Nullable="false"/>
        <Property Name="severity" Type="Edm.String" Nullable="false"/>
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="month" Type="Edm.String"/>
        <Property Name="merchant" Type="Edm.String"/>
        <Property Name="category_main" Type="Edm.String"/>
        <Property Name="category_sub" Type="Edm.String"/>
        <Property Name="amount_chf" Type="Edm.Double" Nullable="false"/>
        <Property Name="baseline_chf" Type="Edm.Double"/>
        <Property Name="count" Type="Edm.Int32"/>
        <Property Name="booking_text" Type="Edm.String"/>
        <Property Name="transaction_id" Type="Edm.String"/>
        <Property Name="transaction_ids" Type="Collection(Edm.String)"/>
      </EntityType>

      <ComplexType Name="NextSalary">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="amount_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="FreeToSpend">
        <Property Name="expected_chf" Type="Edm.Double"/>
        <Property Name="lower_chf" Type="Edm.Double"/>
        <Property Name="upper_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="TightDate">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="days_until" Type="Edm.Int32"/>
        <Property Name="days_before_salary" Type="Edm.Int32"/>
        <Property Name="projected_balance_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="KnownPayment">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="label" Type="Edm.String"/>
        <Property Name="amount_chf" Type="Edm.Double"/>
        <Property Name="category" Type="Edm.String"/>
        <Property Name="recurring_id" Type="Edm.String"/>
      </ComplexType>
      <ComplexType Name="SeriesPoint">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="expected_chf" Type="Edm.Double"/>
        <Property Name="lower_chf" Type="Edm.Double"/>
        <Property Name="upper_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="Assumptions">
        <Property Name="variable_baseline_method" Type="Edm.String"/>
        <Property Name="band_method" Type="Edm.String"/>
        <Property Name="excluded_outliers" Type="Collection(Edm.String)"/>
        <Property Name="interest_applied" Type="Edm.Boolean"/>
        <Property Name="salary_day_detected" Type="Edm.Boolean"/>
        <Property Name="variable_baseline_months_used" Type="Edm.Int32"/>
        <Property Name="notes" Type="Collection(Edm.String)"/>
      </ComplexType>
      <ComplexType Name="ForecastResult">
        <Property Name="as_of" Type="Edm.Date"/>
        <Property Name="horizon" Type="Edm.String"/>
        <Property Name="horizon_end" Type="Edm.Date"/>
        <Property Name="opening_balance_chf" Type="Edm.Double"/>
        <Property Name="next_salary" Type="Forecast.NextSalary"/>
        <Property Name="free_to_spend" Type="Forecast.FreeToSpend"/>
        <Property Name="tight_date" Type="Forecast.TightDate"/>
        <Property Name="known_payments" Type="Collection(Forecast.KnownPayment)"/>
        <Property Name="series" Type="Collection(Forecast.SeriesPoint)"/>
        <Property Name="assumptions" Type="Forecast.Assumptions"/>
      </ComplexType>

      <ComplexType Name="DiffPoint">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="diff_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="Diff">
        <Property Name="monthly_chf" Type="Edm.Double"/>
        <Property Name="cumulative_series" Type="Collection(Forecast.DiffPoint)"/>
        <Property Name="total_at_horizon_chf" Type="Edm.Double"/>
        <Property Name="tight_date_shift_days" Type="Edm.Int32"/>
      </ComplexType>
      <ComplexType Name="SimulateResult">
        <Property Name="baseline" Type="Forecast.ForecastResult"/>
        <Property Name="scenario" Type="Forecast.ForecastResult"/>
        <Property Name="diff" Type="Forecast.Diff"/>
      </ComplexType>

      <ComplexType Name="Adjustment">
        <Property Name="type" Type="Edm.String" Nullable="false"/>
        <Property Name="recurring_id" Type="Edm.String"/>
        <Property Name="effective_from" Type="Edm.Date"/>
        <Property Name="delta_chf" Type="Edm.Double"/>
        <Property Name="label" Type="Edm.String"/>
        <Property Name="amount_chf" Type="Edm.Double"/>
        <Property Name="interval" Type="Edm.String"/>
        <Property Name="start_date" Type="Edm.Date"/>
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="category_main" Type="Edm.String"/>
        <Property Name="category_sub" Type="Edm.String"/>
        <Property Name="percent" Type="Edm.Double"/>
      </ComplexType>

      <Function Name="GetForecast">
        <Parameter Name="horizon" Type="Edm.String"/>
        <Parameter Name="as_of" Type="Edm.Date"/>
        <ReturnType Type="Forecast.ForecastResult"/>
      </Function>

      <Action Name="Simulate">
        <Parameter Name="horizon" Type="Edm.String"/>
        <Parameter Name="as_of" Type="Edm.Date"/>
        <Parameter Name="adjustments" Type="Collection(Forecast.Adjustment)"/>
        <ReturnType Type="Forecast.SimulateResult"/>
      </Action>

      <EntityContainer Name="Container">
        <EntitySet Name="RecurringPayments" EntityType="Forecast.RecurringPayment"/>
        <EntitySet Name="Alerts" EntityType="Forecast.Alert"/>
        <FunctionImport Name="GetForecast" Function="Forecast.GetForecast"/>
        <ActionImport Name="Simulate" Action="Forecast.Simulate"/>
      </EntityContainer>

    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""
