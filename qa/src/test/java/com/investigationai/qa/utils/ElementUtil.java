package com.investigationai.qa.utils;

import org.openqa.selenium.Keys;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;

import com.investigationai.qa.driver.DriverFactory;

public class ElementUtil {
    private WebDriver driver;

    public ElementUtil(WebDriver driver) {
        this.driver = driver;
    }

    public void click(WebElement element) {
        WaitUtils.visible(driver, element).click();
    }


    public void pressEnter(WebElement element){
        WaitUtils.visible(driver, element).sendKeys(Keys.ENTER);
    }

    public String getText(WebElement element) {
        WaitUtils.visible(driver, element);
        return element.getText();
    }

    public void type(WebElement element, String text) {
        WaitUtils.visible(driver, element);
        element.clear();
        element.sendKeys(text);
    }

    public void sendKeys(WebElement element, String text) {
        WaitUtils.visible(driver, element).sendKeys(text);
    }


    public boolean isDisplayed(WebElement element) {
        return WaitUtils.visible(driver, element).isDisplayed();
    }

    public String getAttribute(WebElement element, String attribute) {
        return WaitUtils.visible(driver, element).getAttribute(attribute);
    }


    public void refreshPage() {
        DriverFactory.getDriver().navigate().refresh();
    }
}
