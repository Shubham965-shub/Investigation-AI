package com.investigationai.qa.modal.rating;

import java.util.List;

import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;

public class RatingModal {

    @FindBy(xpath = "//div[@role='radiogroup']//button[@role='radio']")
    private List<WebElement> ratingStars;

    public RatingModal(WebDriver driver) {
        PageFactory.initElements(driver, this);
    }

    public void selectRating(int rating) {
        if (rating < 1 || rating > 5) {
            throw new IllegalArgumentException("Rating must be between 1 and 5");
        }

        if (ratingStars == null) {
            throw new RuntimeException("Rating elements are not initialized");
        }
        if (ratingStars.isEmpty()) {
            throw new RuntimeException("Nop Rating found in this page.");
        }
        ratingStars.get(rating - 1).click();
    }

    public int getSelectedRating() {
        if (ratingStars == null || ratingStars.isEmpty()) {
            return 0;
        }
        for (int i = 0; i < ratingStars.size(); i++) {
            String checked = ratingStars.get(i).getAttribute("aria-checked");
            if ("true".equalsIgnoreCase(checked)) {
                return i + 1;
            }

        }
        return 0;
    }

    public boolean isRatingSelected(int expectedRating) {
        return getSelectedRating() == expectedRating;
    }

}
